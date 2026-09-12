"""Five evidence predicates with bounded discovery and independent publication checks."""
from collections import defaultdict
from datetime import date
import json
import re
import time

from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

from .estate import AMOUNTS, IDS, cents, money

VERSION = 'official-rules-v1'
MAX_LEADS = 128
MAX_EDGES = 10_000
MAX_HOPS = 4
MAX_DAYS = 30
PESO_TOLERANCE_PERCENT = 2
SCHEMES = {'phantom_vendor', 'kickback', 'round_tripping', 'threshold_splitting', 'revenue_inflation'}


class Witness(BaseModel):
    model_config = ConfigDict(extra='forbid')
    author: str = Field(min_length=1, max_length=200)
    delivered: bool
    date: str


class DocumentaryTerms(BaseModel):
    """Optional literal facts in a contract, never executable instructions."""
    model_config = ConfigDict(extra='forbid')
    type: Literal['delivery_terms', 'payment_policy', 'purchase_policy', 'funding_terms']
    valid_until: str
    invoice_uuid: str = ''
    payment_condition: Literal['delivery', 'advance', 'unconditional'] = 'unconditional'
    witnesses: list[Witness] = Field(default_factory=list, max_length=20)
    employee_benefits: Literal['prohibited', 'permitted', 'unknown'] = 'unknown'
    commercial_purpose: Literal['none', 'loan', 'refund', 'trade', 'unknown'] = 'unknown'
    approval_limit_pesos: str = '0'
    authorized_approvers: list[str] = Field(default_factory=list, max_length=50)
    aggregation_days: int = Field(default=1, ge=1, le=30)
    aggregate_by: Literal['vendor_requester_description'] = 'vendor_requester_description'


def terms(row):
    try:
        result = DocumentaryTerms.model_validate_json(row['scope_text'])
        date.fromisoformat(result.valid_until)
        for witness in result.witnesses:
            date.fromisoformat(witness.date)
        cents(result.approval_limit_pesos)
        return result
    except (ValueError, TypeError):
        return None


def mentions(text, identity):
    return re.search(r'(?<![\w:-])' + re.escape(identity) + r'(?![\w:-])', str(text or '')) is not None


def ref(table, row):
    return (table, str(row[IDS[table]]))


def investigate(estate, seed, company_rfc, *, seconds=90, cancelled=None):
    if type(seed) is not int or seed < 0 or not isinstance(company_rfc, str) or not company_rfc.strip():
        raise ValueError('Provide a nonnegative estate seed and company RFC')
    started = time.perf_counter()
    rows = estate.rows
    findings, leads, log = [], [], []
    counters = {'edges': 0, 'truncated': False}
    company = rows['vendors'].get(company_rfc)
    company_account = company['bank_clabe'] if company else None
    contracts = [(r, terms(r)) for r in rows['contracts'].values()]
    warnings = []
    if not company_account:
        warnings.append('Company account ownership is missing from vendors; company-origin payment attribution cannot be substantiated.')
    unparsed = sum(t is None for _, t in contracts)
    if unparsed:
        warnings.append(f'{unparsed} contract texts have no recognized typed terms. Their prose was not treated as an instruction or verified rule.')

    def stop():
        result = (time.perf_counter() - started >= seconds or len(leads) >= MAX_LEADS or
                  counters['edges'] >= MAX_EDGES or (cancelled and cancelled.is_set()))
        if result:
            counters['truncated'] = True
        return result

    def documents(vendor, kind, when, invoice=''):
        return [(r, t) for r, t in contracts if t and r['vendor_rfc'] == vendor and t.type == kind
                and r['start_date'] <= when <= t.valid_until and (not invoice or t.invoice_uuid == invoice)]

    def consider(kind, entity, evidence, rule, amount, trail, supported, reason, tools, other_entities=()):
        if stop():
            return
        evidence = list(dict.fromkeys(evidence))
        lid = f'L{len(leads)+1:04d}'
        entry = {'lead_id': lid, 'entity': entity, 'signal': kind, 'reason': reason,
                 'tool_calls_made': tools, 'closed_by': 'validator',
                 'evidence_examined': [f'{t}:{r}' for t, r in evidence], 'state': 'inconclusive'}
        log.append({'step': len(log)+1, 'lead_id': lid, 'hypothesis': kind, 'tools': tools,
                    'evidence': entry['evidence_examined'], 'alternative_review': reason, 'rule_version': VERSION})
        if supported and amount > 0:
            exhibits = [{'exhibit_id': f'{lid}-EX{i+1:02d}', 'source_table': t, 'record_id': rid,
                         'note': exhibit_note(t, estate.row(t, rid))} for i, (t, rid) in enumerate(evidence)]
            exhibit_map = {(e['source_table'], e['record_id']): e['exhibit_id'] for e in exhibits}
            candidate = {'scheme_type': kind, 'entities': list(dict.fromkeys([entity, *other_entities])),
                         'narrative': reason, 'rule_broken': rule, 'peso_amount': money(amount),
                         'confidence': 'probable', 'exhibits': exhibits,
                         'money_trail': [{'from': tx['from_clabe'], 'to': tx['to_clabe'], 'amount': tx['amount'],
                                          'date': tx['date'], 'exhibit_id': exhibit_map[ref('bank_txns', tx)]} for tx in trail],
                         'amount_definition': 'Documented exposure in the cited records; not legal guilt or demonstrated loss.',
                         'rule_version': VERSION, 'lead_id': lid}
            errors = validate_finding(estate, candidate)
            if not errors:
                findings.append(candidate)
                entry['state'] = 'substantiated'
            else:
                entry['reason'] += ' Publication declined: ' + '; '.join(errors)
        leads.append(entry)

    outgoing = defaultdict(list)
    for tx in rows['bank_txns'].values():
        outgoing[tx['from_clabe']].append(tx)
    for txs in outgoing.values():
        txs.sort(key=lambda tx: (tx['date'], tx['txn_id']))

    def paths(root):
        pending = [([root], {root['from_clabe'], root['to_clabe']})]
        while pending and not stop():
            path, seen = pending.pop(0)
            yield path
            if len(path) >= MAX_HOPS:
                continue
            for tx in outgoing.get(path[-1]['to_clabe'], []):
                counters['edges'] += 1
                if stop():
                    break
                if not path[-1]['date'] < tx['date'] or (date.fromisoformat(tx['date']) - date.fromisoformat(root['date'])).days > MAX_DAYS:
                    continue
                if tx['to_clabe'] == root['from_clabe']:
                    yield path + [tx]
                elif tx['to_clabe'] not in seen:
                    pending.append((path + [tx], seen | {tx['to_clabe']}))

    employees = defaultdict(list)
    for employee in rows['employees'].values():
        if employee['bank_clabe']:
            employees[employee['bank_clabe']].append(employee)

    for invoice in rows['invoices'].values():
        if stop():
            break
        iid = invoice['uuid']
        vendor = rows['vendors'].get(invoice['issuer_rfc'])
        related = [r for r in rows['ledger'].values() if r['invoice_uuid'] == iid]
        base = [ref('invoices', invoice)] + [ref('ledger', r) for r in related]
        if invoice['issuer_rfc'] == company_rfc:
            revenue = [r for r in related if str(r['account_name']).casefold() in ('ingresos', 'revenue', 'ventas', 'sales revenue')]
            net = sum(cents(r['credit']) - cents(r['debit']) for r in revenue)
            if invoice['status'] == 'cancelado':
                evidence = base + ([ref('vendors', company)] if company else [])
                consider('revenue_inflation', 'RFC:' + company_rfc, evidence,
                         'recognition-cancelled-v1: cancelled CFDI must not remain recognized as unreversed revenue',
                         net, [], net > 0 and net == cents(invoice['total']),
                         (f"Cancelled invoice {iid} remains credited to revenue at MXN {money(net):.2f}, after all supplied reversals. "
                          'This establishes recorded revenue contrary to cancellation, not intent. Missing later adjustments remain a visibility gap.' if net > 0 else
                          f"Examined invoice {iid} and all linked revenue entries. Reversal debits offset the credits; no positive unreversed revenue remains."),
                         ['lookup_invoice', 'reconcile_revenue', 'test_reversals'])
            continue
        if not vendor or invoice['receiver_rfc'] != company_rfc:
            continue
        base.append(ref('vendors', vendor))
        paid = [tx for tx in rows['bank_txns'].values() if company_account and tx['from_clabe'] == company_account
                and tx['to_clabe'] == vendor['bank_clabe'] and mentions(tx['reference'], iid)]
        refunds = [tx for tx in rows['bank_txns'].values() if company_account and tx['to_clabe'] == company_account
                   and tx['from_clabe'] == vendor['bank_clabe'] and mentions(tx['reference'], iid)]
        sat = rows['efos_list'].get(vendor['rfc'])
        delivery_docs = documents(vendor['rfc'], 'delivery_terms', invoice['issue_date'], iid)
        if delivery_docs or sat:
            evidence = base + [ref('bank_txns', tx) for tx in paid + refunds] + [ref('contracts', r) for r, _ in delivery_docs]
            if sat:
                evidence.append(ref('efos_list', sat))
            corroborated = False
            if len(delivery_docs) == 1 and paid:
                _, doc = delivery_docs[0]
                witnesses = doc.witnesses
                corroborated = (doc.payment_condition == 'delivery' and len({w.author for w in witnesses if not w.delivered
                                and w.author not in (vendor['rfc'], company_rfc) and w.date >= max(tx['date'] for tx in paid)}) >= 2
                                and not any(w.delivered for w in witnesses))
            amount = sum(cents(tx['amount']) for tx in paid) - sum(cents(tx['amount']) for tx in refunds)
            expense = sum(cents(r['debit']) - cents(r['credit']) for r in related
                          if str(r['account_name']).casefold() in ('gastos', 'expenses', 'gastos operativos'))
            supported = (corroborated and not refunds and len(paid) == 1 and amount == cents(invoice['total'])
                         and invoice['status'] == 'vigente' and expense == amount)
            reason = (f"Invoice {iid} was paid despite delivery-conditioned terms and two distinct supplied non-delivery attestations. "
                      'No delivered attestation or refund appears in the examined records. The finding is probable fictitious-service exposure; supplier existence and document authenticity are unverified.' if supported else
                      f"Examined invoice {iid}, payment/refund records, available contract and SAT evidence. "
                      'A listing or absent delivery alone does not establish fictitious services; contradictory, missing or unreconciled corroboration prevents publication.')
            if not supported:
                reason += f' Matched payments: {len(paid)}; refunds: {len(refunds)}; applicable delivery contracts: {len(delivery_docs)}.'
                for contract_row, doc in delivery_docs:
                    reason += f' Contract {contract_row["contract_id"]}: condition {doc.payment_condition}; {sum(w.delivered for w in doc.witnesses)} delivered attestations and {sum(not w.delivered for w in doc.witnesses)} non-delivery attestations.'
            consider('phantom_vendor', 'RFC:' + vendor['rfc'], evidence, 'delivery-terms-v1: payment requires documented delivery',
                     amount, paid[:1], supported, reason, ['lookup_supplier', 'reconcile_payments', 'check_delivery', 'test_refunds'])
        for root in paid:
            for path in paths(root):
                if len(path) < 2:
                    continue
                last = path[-1]
                owners = employees.get(last['to_clabe'], [])
                closed = last['to_clabe'] == company_account
                if not owners and not closed:
                    continue
                kind = 'round_tripping' if closed else 'kickback'
                docs = documents(vendor['rfc'], 'funding_terms' if closed else 'payment_policy', root['date'], iid)
                evidence = base + [ref('bank_txns', tx) for tx in path] + [ref('contracts', r) for r, _ in docs]
                if company:
                    evidence.append(ref('vendors', company))
                evidence += [ref('employees', owner) for owner in owners]
                for tx in path:
                    evidence += [ref('vendors', v) for v in rows['vendors'].values() if v['bank_clabe'] in (tx['from_clabe'], tx['to_clabe'])]
                linked = all(mentions(tx['reference'], iid) for tx in path)
                known = all(len([v for v in rows['vendors'].values() if v['bank_clabe'] == tx['from_clabe']]) == 1 for tx in path)
                unrelated_refunds = [tx for tx in refunds if not closed or tx['txn_id'] != last['txn_id']]
                supported = (len(docs) == 1 and linked and known and not unrelated_refunds and len(paid) == 1
                             and cents(root['amount']) == cents(invoice['total']) and docs[0][1].valid_until >= last['date'])
                if closed:
                    supported = supported and docs[0][1].commercial_purpose == 'none' if docs else False
                    reason = (f"The dated trail linked to invoice {iid} returns funds to the original company account. "
                              'Supplied funding terms explicitly exclude commercial purpose. Exposure counts the original invoice once, not every hop. '
                              'Commingling prevents proof that identical pesos travelled.' if supported else
                              f"The trail for {iid} closes, but a cycle can be a refund, loan or legitimate internal movement. "
                              'Missing or conflicting noncommercial-purpose documentation, ownership or invoice linkage prevents publication.')
                    rule = 'noncommercial-funding-v1: documented noncommercial recycling of an invoice payment'
                else:
                    supported = (supported and len(owners) == 1 and docs[0][1].employee_benefits == 'prohibited'
                                 and not any(v['bank_clabe'] == last['to_clabe'] for v in rows['vendors'].values())) if docs else False
                    if owners:
                        supported = supported and all(o['hire_date'] and o['hire_date'] <= last['date'] for o in owners)
                    reason = (f"Invoice {iid} has a connected dated payment trail to a uniquely identified employee account, contrary to the supplied benefit prohibition. "
                              f"Observed employee receipt is MXN {money(cents(last['amount'])):.2f}; claimed exposure is the original invoice payment. "
                              'This supports a probable prohibited benefit, not proof of intent or identical pesos.' if supported else
                              f"Investigated the employee-bound trail for {iid}. Shared institution, uncertain ownership, permitted benefits, "
                              'missing prohibition or incomplete invoice linkage cannot substantiate a kickback.')
                    rule = 'employee-benefit-v1: supplied contract prohibits employee benefits'
                if not supported:
                    reason += f' Invoice-linked path: {linked}; unambiguous sender ownership: {known}; employee owners: {len(owners)}; applicable terms: {len(docs)}.'
                    for contract_row, doc in docs:
                        value = doc.commercial_purpose if closed else doc.employee_benefits
                        reason += f' Contract {contract_row["contract_id"]} records {"commercial purpose" if closed else "employee benefits"} as {value}.'
                consider(kind, 'RFC:' + vendor['rfc'], evidence, rule, cents(invoice['total']), path, supported, reason,
                         ['trace_funds', 'lookup_ownership', 'check_contract', 'test_refund_loan_permission'],
                         [o['emp_id'] if o['emp_id'].startswith('EMP:') else 'EMP:' + o['emp_id'] for o in owners])

    groups = defaultdict(list)
    for po in rows['purchase_orders'].values():
        groups[(po['vendor_rfc'], po['requester'], po['description'])].append(po)
    for (vendor_rfc, _, _), orders in sorted(groups.items(), key=lambda item: str(item[0])):
        orders.sort(key=lambda r: (r['date'], r['po_id']))
        if stop():
            break
        if len(orders) < 2:
            continue
        docs = documents(vendor_rfc, 'purchase_policy', orders[0]['date'])
        vendor = rows['vendors'].get(vendor_rfc)
        evidence = [ref('purchase_orders', po) for po in orders] + [ref('contracts', r) for r, _ in docs]
        if vendor:
            evidence.append(ref('vendors', vendor))
        total = sum(cents(po['amount']) for po in orders)
        supported = False
        if len(docs) == 1:
            _, doc = docs[0]
            limit = cents(doc.approval_limit_pesos)
            supported = (bool(doc.authorized_approvers) and limit > 0 and total > limit
                         and all(cents(po['amount']) < limit and po['approver'] not in doc.authorized_approvers for po in orders)
                         and all(po['date'] <= doc.valid_until for po in orders)
                         and (date.fromisoformat(orders[-1]['date']) - date.fromisoformat(orders[0]['date'])).days < doc.aggregation_days)
        reason = ('Orders ' + ', '.join(po['po_id'] for po in orders[:12]) +
                  (' split the same vendor/requester/purpose obligation within the supplied aggregation window. Each is below the documented limit, '
                   'but their total exceeds it without any required approver. This proves the supplied approval-rule discrepancy, not deliberate evasion.' if supported else
                   ' were compared with supplied approval policies. No unique applicable aggregation rule and unapproved over-limit group was substantiated; recurring purchases or authorized approvals remain benign explanations.'))
        if not supported and len(docs) == 1:
            contract_row, doc = docs[0]
            approved = sum(po['approver'] in doc.authorized_approvers for po in orders)
            reason += f' Contract {contract_row["contract_id"]} specifies MXN {doc.approval_limit_pesos}; {approved}/{len(orders)} orders have an authorized approver.'
        consider('threshold_splitting', 'RFC:' + vendor_rfc, evidence, 'aggregate-approval-v1: supplied purchase policy requires aggregate approval',
                 total, [], supported and bool(vendor), reason, ['group_purchase_orders', 'lookup_approval_policy', 'test_authorization'])

    # Explicitly retain unsupported bank visibility signals, including non-invoice flows.
    covered = {e['record_id'] for f in findings for e in f['exhibits'] if e['source_table'] == 'bank_txns'}
    for tx in rows['bank_txns'].values():
        if stop():
            break
        if tx['txn_id'] not in covered and tx['from_clabe'] == company_account:
            entity = next(('RFC:' + v['rfc'] for v in rows['vendors'].values() if v['bank_clabe'] == tx['to_clabe']), 'RFC:' + company_rfc)
            observed = []
            for path in paths(tx):
                if len(path) > 1:
                    observed.extend(ref('bank_txns', leg) for leg in path)
            consider('unresolved_payment', entity, [ref('bank_txns', tx), *observed], '', 0, [], False,
                     f"Examined bank_txns:{tx['txn_id']}. No validated scheme is supported by the available invoice, ownership and policy links. "
                     'Bounded downstream paths were examined; an ordinary or unallocated payment or cycle is not an accusation.', ['lookup_payment', 'trace_funds', 'test_available_links'])
    return {'seed': seed, 'company_rfc': company_rfc, 'estate_sha256': estate.identity,
            'findings': findings, 'leads_not_pursued': [l for l in leads if l['state'] != 'substantiated'],
            'investigation_log': log, 'status': 'incomplete' if counters['truncated'] else 'offline_complete',
            'run_metadata': {'llm_calls': 0, 'mxn_cost': 0.0, 'wall_clock_seconds': round(time.perf_counter()-started, 6),
                             'deterministic': True, 'mode': 'offline', 'cost_by_role': {},
                             'determinism_scope': 'Stable findings and decisions; wall-clock telemetry varies. Replay preserves the completed artifact.'},
            'limits': {'max_leads': MAX_LEADS, 'max_edges': MAX_EDGES, 'max_hops': MAX_HOPS, 'max_days': MAX_DAYS,
                       'examined_edges': counters['edges'], 'truncated': counters['truncated']},
            'rule_version': VERSION, 'warnings': warnings}


def exhibit_note(table, row):
    return {'invoices': 'Identifies invoice parties, status and the gross invoiced amount.',
            'ledger': 'Records the linked accounting entry; balancing entries are not added as exposure.',
            'bank_txns': 'Records dated transfer endpoints, amount and supplied reference.',
            'vendors': 'Supplies the entity identity and asserted account ownership.',
            'employees': 'Supplies the employee identity, hire date and asserted account ownership.',
            'contracts': 'Supplies the contractual condition or documented policy examined.',
            'purchase_orders': 'Records requester, approver, purpose and purchase amount.',
            'efos_list': 'Attributes the listed SAT status and publication date; does not itself prove fraud.'}[table]


def validate_finding(estate, finding):
    errors, amounts, seen, exhibits = [], defaultdict(int), set(), {}
    if finding.get('scheme_type') not in SCHEMES:
        errors.append('Unknown scheme type')
    if finding.get('confidence') not in ('proven', 'probable'):
        errors.append('Invalid confidence')
    if not finding.get('rule_broken') or not 0 < len(finding.get('narrative', '').split()) <= 150:
        errors.append('Missing rule or invalid narrative length')
    for ex in finding.get('exhibits', []):
        key = (ex.get('source_table'), ex.get('record_id'))
        if key in seen or ex.get('exhibit_id') in exhibits:
            errors.append('Duplicate exhibit')
            continue
        seen.add(key)
        exhibits[ex.get('exhibit_id')] = key
        try:
            row = estate.row(*key)
            if key[0] in AMOUNTS:
                amounts[key[0]] += cents(row[AMOUNTS[key[0]]])
        except (KeyError, TypeError):
            errors.append('Nonexistent source record')
    if len(seen) < 3:
        errors.append('At least three unique exhibits required')
    try:
        claimed = cents(finding.get('peso_amount'))
        if claimed <= 0 or not amounts or not any(abs(claimed-value)*100 <= 2*max(value, 100) for value in amounts.values()):
            errors.append('Peso amount fails per-table reconciliation')
    except ValueError:
        errors.append('Invalid peso amount')
    previous = None
    for step in finding.get('money_trail', []):
        key = exhibits.get(step.get('exhibit_id'))
        if not key or key[0] != 'bank_txns':
            errors.append('Trail step lacks a bank exhibit')
            continue
        row = estate.row(*key)
        if (step.get('from'), step.get('to'), step.get('date'), step.get('amount')) != (row['from_clabe'], row['to_clabe'], row['date'], row['amount']):
            errors.append('Trail does not match original transfer')
        if previous and (previous['to'] != step['from'] or previous['date'] >= step['date']):
            errors.append('Trail is disconnected or not time ordered')
        previous = step
    for entity in finding.get('entities', []):
        if entity.startswith('RFC:'):
            supported = ('vendors', entity[4:]) in seen or any(t == 'invoices' and entity[4:] in (estate.row(t, r)['issuer_rfc'], estate.row(t, r)['receiver_rfc']) for t, r in seen)
        elif entity.startswith('EMP:'):
            supported = ('employees', entity) in seen or ('employees', entity[4:]) in seen
        else:
            supported = False
        if not supported:
            errors.append('Entity lacks a supporting exhibit')
    if not finding.get('entities'):
        errors.append('Missing entities')
    return errors
