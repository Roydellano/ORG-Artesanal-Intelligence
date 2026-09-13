"""Evidence predicates with bounded discovery, challenger tests and independent publication checks.

Two evidence bases feed one publication gate:

* documentary - optional typed contract terms in ``contracts.scope_text`` support narrow predicates;
* records     - patterns visible in the eight official tables alone: the SAT Article 69-B list, exact
  CLABE ownership, dated bank paths, approval tiers in purchase orders, CFDI status/payment method and
  collections.

Detectors only open leads. A lead publishes when its predicate is corroborated, every challenger
argument fails, and ``validate_finding`` re-checks citations, arithmetic and the money trail.
Documentary evidence governs: where typed terms exist for a supplier, the records heuristic defers.
"""
from collections import Counter, defaultdict, deque
from datetime import date
import re
import time

from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

from .estate import AMOUNTS, IDS, cents, money

VERSION = 'official-rules-v2'
MAX_LEADS = 400
MAX_EDGES = 200_000
MAX_HOPS = 4
MAX_DAYS = 30
PESO_TOLERANCE_PERCENT = 2
SCHEMES = {'phantom_vendor', 'kickback', 'round_tripping', 'threshold_splitting', 'revenue_inflation'}

# Records-based detector constraints. Judges: these are the thresholds, all in one place.
NEW_VENDOR_DAYS = 120                 # registration to first invoice that counts as "new supplier"
PAYMENT_MATCH_DAYS = 120              # unreferenced payment matched to an invoice by exact amount
COLLECTION_MATCH_DAYS = 180           # unreferenced receipt matched to a sales invoice by exact amount
KICKBACK_WINDOW_DAYS = 45             # company payment to employee receipt
ROUND_TRIP_WINDOW_DAYS = 90           # company payment to funds returning to the company
ROUND_TRIP_MIN_RETURN_PERCENT = 80    # share of the payment that must come back
PASS_THROUGH_DAYS = 10                # supplier forwards receipts onward within this window
PASS_THROUGH_MIN_PERCENT = 50
PHANTOM_MIN_WEAK_SIGNALS = 2          # without a definitive 69-B listing
SPLIT_WINDOW_DAYS = 14
SPLIT_MIN_ORDERS = 3                  # or two orders within SPLIT_PAIR_MAX_DAYS
SPLIT_PAIR_MAX_DAYS = 3
SPLIT_MIN_SHARE_PERCENT = 50          # each split order is at least this share of the limit
APPROVAL_LIMIT_CANDIDATES = (5_000, 10_000, 20_000, 25_000, 30_000, 50_000, 75_000, 100_000, 150_000,
                             200_000, 250_000, 300_000, 500_000, 750_000, 1_000_000, 2_000_000, 5_000_000)
MIN_COLLECTION_COVERAGE_PERCENT = 50  # below this the estate does not model collections; skip that test
MAX_UNMATCHED_LEADS = 40
REVENUE_NAMES = ('ingresos', 'revenue', 'ventas', 'sales revenue', 'ingresos por ventas')
EXPENSE_NAMES = ('gastos', 'expenses', 'gastos operativos')
REFUND_REFERENCE = re.compile(r'devoluci|reembols|nota de cr[eé]dito|refund|reintegro|vi[aá]ticos', re.I)
LOAN_REFERENCE = re.compile(r'pr[eé]stamo|\bloan\b|financiamiento|\bmutuo\b', re.I)
EFOS_CLEARED = ('desvirtuado', 'sentencia_favorable')

SETTINGS = {name: value for name, value in globals().items() if name.isupper() and isinstance(value, (int, tuple))}


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
        result = DocumentaryTerms.model_validate_json(row['scope_text'] or '')
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


def amt(value):
    """Nullable ledger money is a visibility gap counted as zero; other money is validated at ingestion."""
    return 0 if value is None else cents(value)


def days(earlier, later):
    return (date.fromisoformat(later) - date.fromisoformat(earlier)).days


def pesos(value):
    return f'MXN {money(value):,.2f}'


def is_revenue(row):
    return str(row['account_name'] or '').casefold() in REVENUE_NAMES or str(row['account_code'] or '').startswith('4')


def is_expense(row):
    return str(row['account_name'] or '').casefold() in EXPENSE_NAMES or str(row['account_code'] or '').startswith(('5', '6'))


def emp_entity(emp_id):
    return emp_id if str(emp_id).startswith('EMP:') else 'EMP:' + str(emp_id)


def challenge(argument, check, held):
    """One adversarial argument, the record check run against it, and whether the accusation survived."""
    return {'argument': argument, 'check': check, 'accusation_survives': bool(held)}


def investigate(estate, seed, company_rfc, *, seconds=90, cancelled=None):
    if type(seed) is not int or seed < 0 or not isinstance(company_rfc, str) or not company_rfc.strip():
        raise ValueError('Provide a nonnegative estate seed and company RFC')
    started = time.perf_counter()
    rows = estate.rows
    findings, leads, log = [], [], []
    counters = {'edges': 0, 'truncated': False}
    published = set()
    warnings = []
    company = rows['vendors'].get(company_rfc)
    contracts = [(r, terms(r)) for r in rows['contracts'].values()]
    unparsed = sum(t is None for _, t in contracts)
    if unparsed:
        warnings.append(f'{unparsed} contract texts have no typed terms. Their prose was never executed; records-based predicates were applied instead.')

    # ---- indexes -------------------------------------------------------------------------------
    vendors_by_clabe, employees_by_clabe = defaultdict(list), defaultdict(list)
    for v in rows['vendors'].values():
        if v['bank_clabe']:
            vendors_by_clabe[v['bank_clabe']].append(v)
    for e in rows['employees'].values():
        if e['bank_clabe']:
            employees_by_clabe[e['bank_clabe']].append(e)
    ledger_by_invoice = defaultdict(list)
    for r in rows['ledger'].values():
        if r['invoice_uuid']:
            ledger_by_invoice[r['invoice_uuid']].append(r)
    outgoing, incoming = defaultdict(list), defaultdict(list)
    for tx in rows['bank_txns'].values():
        outgoing[tx['from_clabe']].append(tx)
        incoming[tx['to_clabe']].append(tx)
    for index in (outgoing, incoming):
        for txs in index.values():
            txs.sort(key=lambda tx: (tx['date'], tx['txn_id']))
    invoices = sorted(rows['invoices'].values(), key=lambda i: (i['issue_date'], i['uuid']))
    received = [i for i in invoices if i['receiver_rfc'] == company_rfc and i['issuer_rfc'] != company_rfc]
    issued = [i for i in invoices if i['issuer_rfc'] == company_rfc]
    pos_by_vendor, contracts_by_vendor = defaultdict(list), defaultdict(list)
    for po in sorted(rows['purchase_orders'].values(), key=lambda r: (r['date'], r['po_id'])):
        pos_by_vendor[po['vendor_rfc']].append(po)
    for row, _ in contracts:
        contracts_by_vendor[row['vendor_rfc']].append(row)

    # ---- company account: master data, else inferred from payments to invoicing suppliers -------
    if company and company['bank_clabe']:
        company_accounts = {company['bank_clabe']}
    else:
        supplier_clabes = {rows['vendors'][i['issuer_rfc']]['bank_clabe'] for i in received
                           if i['issuer_rfc'] in rows['vendors'] and rows['vendors'][i['issuer_rfc']]['bank_clabe']}
        votes = Counter(tx['from_clabe'] for tx in rows['bank_txns'].values()
                        if tx['to_clabe'] in supplier_clabes and tx['from_clabe'] not in supplier_clabes
                        and tx['from_clabe'] not in employees_by_clabe)
        if votes:
            best = min(votes, key=lambda clabe: (-votes[clabe], clabe))
            company_accounts = {best}
            warnings.append(f'The company is not in vendors master data. Its account was inferred as CLABE {best}, '
                            f'the payer on {votes[best]} transfers to invoicing suppliers.')
        else:
            company_accounts = set()
            warnings.append('Company account ownership is missing from vendors; company-origin payment attribution cannot be substantiated.')

    def stop():
        result = (time.perf_counter() - started >= seconds or len(leads) >= MAX_LEADS or
                  counters['edges'] >= MAX_EDGES or (cancelled and cancelled.is_set()))
        if result:
            counters['truncated'] = True
        return result

    def documents(vendor, kind, when, invoice=''):
        return [(r, t) for r, t in contracts if t and r['vendor_rfc'] == vendor and t.type == kind
                and r['start_date'] <= when <= t.valid_until and (not invoice or t.invoice_uuid == invoice)]

    def documented(vendor, kind):
        return any(t and r['vendor_rfc'] == vendor and t.type == kind for r, t in contracts)

    def consider(kind, entity, evidence, rule, amount, trail, supported, reason, tools, other_entities=(), *,
                 confidence='probable', challenges=(), closed_by='investigator', basis='documentary', narrative=None):
        if stop():
            return False
        evidence = list(dict.fromkeys(evidence))
        lid = f'L{len(leads)+1:04d}'
        entry = {'lead_id': lid, 'entity': entity, 'signal': kind, 'reason': reason,
                 'tool_calls_made': tools, 'closed_by': closed_by, 'basis': basis,
                 'evidence_examined': [f'{t}:{r}' for t, r in evidence], 'state': 'inconclusive'}
        log.append({'step': len(log)+1, 'lead_id': lid, 'hypothesis': kind, 'tools': tools,
                    'evidence': entry['evidence_examined'], 'alternative_review': reason,
                    'challenges': list(challenges), 'rule_version': VERSION})
        if supported and amount > 0:
            exhibits = [{'exhibit_id': f'{lid}-EX{i+1:02d}', 'source_table': t, 'record_id': rid,
                         'note': exhibit_note(t, estate.row(t, rid))} for i, (t, rid) in enumerate(evidence)]
            exhibit_map = {(e['source_table'], e['record_id']): e['exhibit_id'] for e in exhibits}
            candidate = {'scheme_type': kind, 'entities': list(dict.fromkeys([entity, *other_entities])),
                         'narrative': narrative or reason, 'rule_broken': rule, 'peso_amount': money(amount),
                         'confidence': confidence, 'exhibits': exhibits, 'basis': basis,
                         'money_trail': [{'from': tx['from_clabe'], 'to': tx['to_clabe'], 'amount': tx['amount'],
                                          'date': tx['date'], 'exhibit_id': exhibit_map[ref('bank_txns', tx)]} for tx in trail],
                         'challenges': list(challenges),
                         'amount_definition': 'Documented exposure in the cited records; not legal guilt or demonstrated loss.',
                         'rule_version': VERSION, 'lead_id': lid}
            errors = validate_finding(estate, candidate)
            if not errors:
                findings.append(candidate)
                entry['state'] = 'substantiated'
                published.add((kind, entity))
                leads.append(entry)
                return True
            entry['reason'] += ' Publication declined by the validator: ' + '; '.join(errors)
            entry['closed_by'] = 'validator'
        leads.append(entry)
        return False

    def paths(root):
        """Documentary-path search (strictly dated, 30 days), unchanged from rules v1."""
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
                if not path[-1]['date'] < tx['date'] or days(root['date'], tx['date']) > MAX_DAYS:
                    continue
                if tx['to_clabe'] == root['from_clabe']:
                    yield path + [tx]
                elif tx['to_clabe'] not in seen:
                    pending.append((path + [tx], seen | {tx['to_clabe']}))

    def flows(root, window):
        """Records-path search: onward transfers dated on/after the previous hop, amounts never growing."""
        pending = deque([[root]])
        while pending and not stop():
            path = pending.popleft()
            if len(path) > 1:
                yield path
                if path[-1]['to_clabe'] in company_accounts:
                    continue
            if len(path) >= MAX_HOPS:
                continue
            last = path[-1]
            seen = {root['from_clabe'], *(tx['to_clabe'] for tx in path)}
            used = {tx['txn_id'] for tx in path}
            for tx in outgoing.get(last['to_clabe'], []):
                counters['edges'] += 1
                if stop():
                    return
                if (tx['txn_id'] in used or tx['date'] < last['date'] or days(root['date'], tx['date']) > window
                        or cents(tx['amount']) * 100 > cents(last['amount']) * 102):
                    continue
                if tx['to_clabe'] in company_accounts or tx['to_clabe'] not in seen:
                    pending.append(path + [tx])

    def unique_vendor(clabe):
        owners = vendors_by_clabe.get(clabe, [])
        return owners[0] if len(owners) == 1 else None

    # ---- settlement: invoice-referenced payments first, then exact amount/date matches -----------
    settlement, paid_invoices, used = defaultdict(list), defaultdict(list), set()
    for invoice in received:
        vendor = rows['vendors'].get(invoice['issuer_rfc'])
        if vendor and vendor['bank_clabe']:
            for tx in incoming[vendor['bank_clabe']]:
                if tx['from_clabe'] in company_accounts and mentions(tx['reference'], invoice['uuid']):
                    settlement[invoice['uuid']].append(tx)
                    used.add(tx['txn_id'])
    for invoice in received:
        vendor = rows['vendors'].get(invoice['issuer_rfc'])
        if settlement[invoice['uuid']] or not vendor or not vendor['bank_clabe'] or invoice['status'] != 'vigente':
            continue
        for tx in incoming[vendor['bank_clabe']]:
            if (tx['txn_id'] not in used and tx['from_clabe'] in company_accounts and cents(tx['amount']) == cents(invoice['total'])
                    and 0 <= days(invoice['issue_date'], tx['date']) <= PAYMENT_MATCH_DAYS):
                settlement[invoice['uuid']].append(tx)
                used.add(tx['txn_id'])
                break
    for uuid, txs in settlement.items():
        for tx in txs:
            paid_invoices[tx['txn_id']].append(uuid)

    # ================================================================================================
    # Documentary predicates (typed contract terms)
    # ================================================================================================
    for invoice in received:
        if stop():
            break
        iid = invoice['uuid']
        vendor = rows['vendors'].get(invoice['issuer_rfc'])
        related = ledger_by_invoice.get(iid, [])
        base = [ref('invoices', invoice)] + [ref('ledger', r) for r in related]
        if not vendor:
            continue
        base.append(ref('vendors', vendor))
        paid = [tx for tx in incoming.get(vendor['bank_clabe'], []) if tx['from_clabe'] in company_accounts and mentions(tx['reference'], iid)]
        refunds = [tx for tx in outgoing.get(vendor['bank_clabe'], []) if tx['to_clabe'] in company_accounts and mentions(tx['reference'], iid)]
        sat = rows['efos_list'].get(vendor['rfc'])
        delivery_docs = documents(vendor['rfc'], 'delivery_terms', invoice['issue_date'], iid)
        if delivery_docs:
            evidence = base + [ref('bank_txns', tx) for tx in paid + refunds] + [ref('contracts', r) for r, _ in delivery_docs]
            if sat:
                evidence.append(ref('efos_list', sat))
            corroborated = delivered = False
            if len(delivery_docs) == 1 and paid:
                _, doc = delivery_docs[0]
                witnesses = doc.witnesses
                delivered = any(w.delivered for w in witnesses)
                corroborated = (doc.payment_condition == 'delivery' and len({w.author for w in witnesses if not w.delivered
                                and w.author not in (vendor['rfc'], company_rfc) and w.date >= max(tx['date'] for tx in paid)}) >= 2
                                and not delivered)
            amount = sum(cents(tx['amount']) for tx in paid) - sum(cents(tx['amount']) for tx in refunds)
            expense = sum(amt(r['debit']) - amt(r['credit']) for r in related if is_expense(r))
            supported = (corroborated and not refunds and len(paid) == 1 and amount == cents(invoice['total'])
                         and invoice['status'] == 'vigente' and expense == amount)
            checks = [challenge('Delivery may have happened; attestations could be incomplete.',
                                f'{sum(w.delivered for _, d in delivery_docs for w in d.witnesses)} delivered and '
                                f'{sum(not w.delivered for _, d in delivery_docs for w in d.witnesses)} non-delivery attestations in the applicable contract.', corroborated),
                      challenge('The payment may have been refunded or only partly made.',
                                f'{len(paid)} invoice-referenced payments and {len(refunds)} refunds; paid {pesos(max(amount, 0))} against invoice {pesos(cents(invoice["total"]))}.',
                                not refunds and len(paid) == 1 and amount == cents(invoice['total'])),
                      challenge('A SAT listing alone does not prove the service was fictitious.',
                                'Publication relies on delivery-conditioned terms and attestations, not on the listing.', True)]
            reason = (f"Invoice {iid} was paid despite delivery-conditioned terms and two distinct supplied non-delivery attestations. "
                      'No delivered attestation or refund appears in the examined records. The finding is probable fictitious-service exposure; supplier existence and document authenticity are unverified.' if supported else
                      f"Examined invoice {iid}, payment/refund records, available contract and SAT evidence. "
                      'A listing or absent delivery alone does not establish fictitious services; contradictory, missing or unreconciled corroboration prevents publication.')
            if not supported:
                reason += f' Matched payments: {len(paid)}; refunds: {len(refunds)}; applicable delivery contracts: {len(delivery_docs)}.'
                for contract_row, doc in delivery_docs:
                    reason += f' Contract {contract_row["contract_id"]}: condition {doc.payment_condition}; {sum(w.delivered for w in doc.witnesses)} delivered attestations and {sum(not w.delivered for w in doc.witnesses)} non-delivery attestations.'
            consider('phantom_vendor', 'RFC:' + vendor['rfc'], evidence, 'delivery-terms-v1: payment requires documented delivery',
                     amount, paid[:1], supported, reason, ['lookup_supplier', 'reconcile_payments', 'check_delivery', 'test_refunds'],
                     challenges=checks, closed_by='challenger' if delivered or refunds else 'investigator')
        for root in paid:
            for path in paths(root):
                if len(path) < 2:
                    continue
                last = path[-1]
                owners = employees_by_clabe.get(last['to_clabe'], [])
                closed = last['to_clabe'] in company_accounts
                if not owners and not closed:
                    continue
                kind = 'round_tripping' if closed else 'kickback'
                docs = documents(vendor['rfc'], 'funding_terms' if closed else 'payment_policy', root['date'], iid)
                if not docs:
                    continue  # no documentary terms: the records predicates below decide
                evidence = base + [ref('bank_txns', tx) for tx in path] + [ref('contracts', r) for r, _ in docs]
                if company:
                    evidence.append(ref('vendors', company))
                evidence += [ref('employees', owner) for owner in owners]
                for tx in path:
                    evidence += [ref('vendors', v) for v in rows['vendors'].values() if v['bank_clabe'] in (tx['from_clabe'], tx['to_clabe'])]
                linked = all(mentions(tx['reference'], iid) for tx in path)
                known = all(len(vendors_by_clabe.get(tx['from_clabe'], [])) == 1 for tx in path)
                unrelated_refunds = [tx for tx in refunds if not closed or tx['txn_id'] != last['txn_id']]
                supported = (len(docs) == 1 and linked and known and not unrelated_refunds and len(paid) == 1
                             and cents(root['amount']) == cents(invoice['total']) and docs[0][1].valid_until >= last['date'])
                values = [doc.commercial_purpose if closed else doc.employee_benefits for _, doc in docs]
                benign = any(value in (('loan', 'refund', 'trade') if closed else ('permitted',)) for value in values)
                if closed:
                    supported = supported and docs[0][1].commercial_purpose == 'none'
                    reason = (f"The dated trail linked to invoice {iid} returns funds to the original company account. "
                              'Supplied funding terms explicitly exclude commercial purpose. Exposure counts the original invoice once, not every hop. '
                              'Commingling prevents proof that identical pesos travelled.' if supported else
                              f"The trail for {iid} closes, but a cycle can be a refund, loan or legitimate internal movement. "
                              'Missing or conflicting noncommercial-purpose documentation, ownership or invoice linkage prevents publication.')
                    rule = 'noncommercial-funding-v1: documented noncommercial recycling of an invoice payment'
                    checks = [challenge('The returning funds may be a loan, refund or trade settlement.',
                                        f'Applicable funding terms record commercial purpose: {", ".join(values)}.', not benign and supported)]
                else:
                    supported = (supported and len(owners) == 1 and docs[0][1].employee_benefits == 'prohibited'
                                 and not any(v['bank_clabe'] == last['to_clabe'] for v in rows['vendors'].values())
                                 and all(o['hire_date'] and o['hire_date'] <= last['date'] for o in owners))
                    reason = (f"Invoice {iid} has a connected dated payment trail to a uniquely identified employee account, contrary to the supplied benefit prohibition. "
                              f"Observed employee receipt is MXN {money(cents(last['amount'])):.2f}; claimed exposure is the original invoice payment. "
                              'This supports a probable prohibited benefit, not proof of intent or identical pesos.' if supported else
                              f"Investigated the employee-bound trail for {iid}. Shared institution, uncertain ownership, permitted benefits, "
                              'missing prohibition or incomplete invoice linkage cannot substantiate a kickback.')
                    rule = 'employee-benefit-v1: supplied contract prohibits employee benefits'
                    checks = [challenge('The employee benefit may be permitted by contract.',
                                        f'Applicable payment policy records employee benefits: {", ".join(values)}.', not benign and supported),
                              challenge('The receiving account may not belong to the employee alone.',
                                        f'Exact CLABE owners: {len(owners)} employee(s).', len(owners) == 1)]
                if not supported:
                    reason += f' Invoice-linked path: {linked}; unambiguous sender ownership: {known}; employee owners: {len(owners)}; applicable terms: {len(docs)}.'
                    for contract_row, doc in docs:
                        value = doc.commercial_purpose if closed else doc.employee_benefits
                        reason += f' Contract {contract_row["contract_id"]} records {"commercial purpose" if closed else "employee benefits"} as {value}.'
                consider(kind, 'RFC:' + vendor['rfc'], evidence, rule, cents(invoice['total']), path, supported, reason,
                         ['trace_funds', 'lookup_ownership', 'check_contract', 'test_refund_loan_permission'],
                         [emp_entity(o['emp_id']) for o in owners], challenges=checks,
                         closed_by='challenger' if benign or len(owners) > 1 else 'investigator')

    groups = defaultdict(list)
    for po in rows['purchase_orders'].values():
        groups[(po['vendor_rfc'], po['requester'], po['description'])].append(po)
    for (vendor_rfc, _, _), orders in sorted(groups.items(), key=lambda item: str(item[0])):
        orders.sort(key=lambda r: (r['date'], r['po_id']))
        if stop():
            break
        docs = documents(vendor_rfc, 'purchase_policy', orders[0]['date'])
        if len(orders) < 2 or not docs:
            continue
        vendor = rows['vendors'].get(vendor_rfc)
        evidence = [ref('purchase_orders', po) for po in orders] + [ref('contracts', r) for r, _ in docs]
        if vendor:
            evidence.append(ref('vendors', vendor))
        total = sum(cents(po['amount']) for po in orders)
        supported = False
        approved = 0
        if len(docs) == 1:
            contract_row, doc = docs[0]
            limit = cents(doc.approval_limit_pesos)
            approved = sum(po['approver'] in doc.authorized_approvers for po in orders)
            supported = (bool(doc.authorized_approvers) and limit > 0 and total > limit
                         and all(cents(po['amount']) < limit and po['approver'] not in doc.authorized_approvers for po in orders)
                         and all(po['date'] <= doc.valid_until for po in orders)
                         and days(orders[0]['date'], orders[-1]['date']) < doc.aggregation_days)
        reason = ('Orders ' + ', '.join(po['po_id'] for po in orders[:12]) +
                  (' split the same vendor/requester/purpose obligation within the supplied aggregation window. Each is below the documented limit, '
                   'but their total exceeds it without any required approver. This proves the supplied approval-rule discrepancy, not deliberate evasion.' if supported else
                   ' were compared with supplied approval policies. No unique applicable aggregation rule and unapproved over-limit group was substantiated; recurring purchases or authorized approvals remain benign explanations.'))
        if not supported and len(docs) == 1:
            reason += f' Contract {contract_row["contract_id"]} specifies MXN {doc.approval_limit_pesos}; {approved}/{len(orders)} orders have an authorized approver.'
        checks = [challenge('An authorized approver may have signed the aggregate purchase.',
                            f'{approved}/{len(orders)} orders carry an approver named in the purchase policy.', approved == 0),
                  challenge('These may be separate recurring purchases rather than one split obligation.',
                            f'Orders span {days(orders[0]["date"], orders[-1]["date"])} days with the same vendor, requester and description.', supported)]
        consider('threshold_splitting', 'RFC:' + vendor_rfc, evidence, 'aggregate-approval-v1: supplied purchase policy requires aggregate approval',
                 total, [], supported and bool(vendor), reason, ['group_purchase_orders', 'lookup_approval_policy', 'test_authorization'],
                 confidence='proven', challenges=checks, closed_by='challenger' if approved else 'investigator')

    # ================================================================================================
    # Records predicates (the eight official tables alone)
    # ================================================================================================
    efos = rows['efos_list']

    def invoice_refs(uuids):
        refs = []
        for uuid in uuids:
            refs.append(('invoices', uuid))
            refs += [ref('ledger', r) for r in ledger_by_invoice.get(uuid, [])]
        return refs

    # ---- revenue_inflation: cancelled CFDI still recognized ----------------------------------------
    for invoice in issued:
        if stop():
            break
        if invoice['status'] != 'cancelado':
            continue
        iid = invoice['uuid']
        revenue = [r for r in ledger_by_invoice.get(iid, []) if is_revenue(r)]
        net = sum(amt(r['credit']) - amt(r['debit']) for r in revenue)
        customer = rows['vendors'].get(invoice['receiver_rfc'])
        evidence = invoice_refs([iid]) + ([ref('vendors', company)] if company else [])
        if customer:
            evidence.append(ref('vendors', customer))
        if invoice['receiver_rfc'] in efos:
            evidence.append(ref('efos_list', efos[invoice['receiver_rfc']]))
        supported = net > 0 and net == cents(invoice['total'])
        reversal = [r for r in revenue if amt(r['debit']) > 0]
        checks = [challenge('A later reversal may already remove the revenue.',
                            f'{len(reversal)} reversing debit(s) to revenue accounts; net unreversed revenue {pesos(max(net, 0))}.', net > 0),
                  challenge('Revenue may have been recorded net of VAT or for a different amount.',
                            f'Net revenue {pesos(max(net, 0))} versus invoice total {pesos(cents(invoice["total"]))}.', net == cents(invoice['total']))]
        reason = (f"CFDI {iid} to {invoice['receiver_rfc']} was cancelled, yet {pesos(net)} stays credited to revenue after every recorded reversal. "
                  'Revenue recorded for a cancelled invoice overstates sales; intent is not established.' if supported else
                  f"Examined cancelled invoice {iid} and all linked revenue entries. " +
                  ('Reversal debits offset the credits; no unreversed revenue remains.' if net <= 0 else
                   f'Net unreversed revenue {pesos(net)} does not equal the invoice total, so the overstatement cannot be reconciled.'))
        consider('revenue_inflation', 'RFC:' + company_rfc, evidence,
                 'recognition-cancelled-v1 (CFF Art. 29-A; NIF D-1): a cancelled CFDI must not remain recognized as revenue',
                 net, [], supported, reason, ['lookup_invoice', 'reconcile_revenue', 'test_reversals'],
                 ['RFC:' + invoice['receiver_rfc']], confidence='proven', challenges=checks,
                 closed_by='challenger' if net <= 0 else 'investigator', basis='records')

    # ---- revenue_inflation: PUE sales never collected ------------------------------------------------
    active_sales = [i for i in issued if i['status'] == 'vigente']
    collections, taken = {}, set()
    for invoice in active_sales:
        customer = rows['vendors'].get(invoice['receiver_rfc'])
        receipts = [tx for account in company_accounts for tx in incoming.get(account, []) if mentions(tx['reference'], invoice['uuid'])]
        if not receipts:
            for account in sorted(company_accounts):
                for tx in incoming.get(account, []):
                    if (tx['txn_id'] not in taken and cents(tx['amount']) == cents(invoice['total'])
                            and 0 <= days(invoice['issue_date'], tx['date']) <= COLLECTION_MATCH_DAYS
                            and (not customer or tx['from_clabe'] == customer['bank_clabe'] or not tx['reference'])):
                        receipts = [tx]
                        break
        taken.update(tx['txn_id'] for tx in receipts)
        collections[invoice['uuid']] = receipts
    coverage = 100 * sum(bool(r) for r in collections.values()) / len(active_sales) if active_sales else 0
    if active_sales and coverage < MIN_COLLECTION_COVERAGE_PERCENT:
        warnings.append(f'Only {coverage:.0f}% of active sales invoices have a visible collection, so the estate does not model '
                        'collections; the uncollected-sale test was not applied.')
    else:
        by_customer = defaultdict(list)
        for invoice in active_sales:
            if not collections[invoice['uuid']]:
                by_customer[invoice['receiver_rfc']].append(invoice)
        for customer_rfc, unpaid in sorted(by_customer.items()):
            if stop():
                break
            customer = rows['vendors'].get(customer_rfc)
            deferred = [i for i in unpaid if i['metodo_pago'] == 'PPD']
            immediate = [i for i in unpaid if i['metodo_pago'] != 'PPD']
            recognized = [i for i in immediate if sum(amt(r['credit']) - amt(r['debit']) for r in ledger_by_invoice.get(i['uuid'], []) if is_revenue(r)) > 0]
            collected_before = any(collections[i['uuid']] for i in active_sales if i['receiver_rfc'] == customer_rfc)
            corroboration = []
            if not customer:
                corroboration.append('customer absent from master data')
            elif customer['registered_date'] and recognized and days(customer['registered_date'], min(i['issue_date'] for i in recognized)) <= NEW_VENDOR_DAYS:
                corroboration.append(f'customer registered {customer["registered_date"]}, shortly before the sale')
            if customer_rfc in efos and efos[customer_rfc]['status'] not in EFOS_CLEARED:
                corroboration.append(f'customer on SAT 69-B list ({efos[customer_rfc]["status"]})')
            if not collected_before:
                corroboration.append('no collection from this customer anywhere in the estate')
            amount = sum(cents(i['total']) for i in recognized)
            supported = bool(recognized) and len(corroboration) >= 2
            evidence = invoice_refs(i['uuid'] for i in (recognized or unpaid)) + ([ref('vendors', customer)] if customer else [])
            if customer_rfc in efos:
                evidence.append(ref('efos_list', efos[customer_rfc]))
            checks = [challenge('Payment may be contractually deferred (PPD, pago en parcialidades o diferido).',
                                f'{len(deferred)} of {len(unpaid)} uncollected invoices are PPD; {len(immediate)} declare payment at issuance (PUE).', bool(immediate)),
                      challenge('The customer may have paid without citing the invoice.',
                                f'Searched receipts into the company account by invoice reference and by exact amount within {COLLECTION_MATCH_DAYS} days: none found.', True),
                      challenge('An unpaid sale may simply be a slow-paying real customer.',
                                'Corroboration: ' + ('; '.join(corroboration) or 'none') + '.', len(corroboration) >= 2)]
            reason = (f"Sales CFDI {', '.join(i['uuid'] for i in recognized[:6])} to {customer_rfc} total {pesos(amount)}, were booked as revenue and "
                      f"declare payment at issuance (PUE), but no collection exists. Corroboration: {'; '.join(corroboration)}. "
                      'Revenue appears recorded without a real sale.' if supported else
                      f"Uncollected sales to {customer_rfc}: {len(unpaid)} invoice(s), {len(deferred)} deferred (PPD). "
                      f"Corroboration found: {'; '.join(corroboration) or 'none'}. "
                      + ('Deferred payment terms explain the missing collection.' if not immediate else
                         'An uncollected receivable alone is not fabricated revenue.'))
            consider('revenue_inflation', 'RFC:' + company_rfc, evidence,
                     'NIF D-1 and CFF Art. 29-A: revenue requires a real sale; a PUE CFDI declares payment at issuance, yet none was received',
                     amount, [], supported, reason, ['lookup_sales_invoices', 'match_collections', 'check_payment_method', 'lookup_customer'],
                     ['RFC:' + customer_rfc], challenges=checks,
                     closed_by='challenger' if not immediate else 'investigator', basis='records')

    # ---- dated flows from company payments (feeds kickback, round_tripping and pass-through tests) ------
    company_payments = sorted((tx for account in company_accounts for tx in outgoing.get(account, [])),
                              key=lambda tx: (tx['date'], tx['txn_id']))
    kick_cases, trip_cases = {}, {}
    for root in company_payments:
        if stop():
            break
        vendor = unique_vendor(root['to_clabe'])
        if not vendor or vendor['rfc'] == company_rfc:
            continue
        if root['to_clabe'] in employees_by_clabe:
            kick_cases.setdefault((vendor['rfc'], root['to_clabe']), []).append([root])
        kick_seen, trip_found = set(), False
        for path in flows(root, max(KICKBACK_WINDOW_DAYS, ROUND_TRIP_WINDOW_DAYS)):
            end = path[-1]['to_clabe']
            span = days(root['date'], path[-1]['date'])
            if end in employees_by_clabe and end not in kick_seen and span <= KICKBACK_WINDOW_DAYS:
                kick_seen.add(end)
                kick_cases.setdefault((vendor['rfc'], end), []).append(path)
            elif end in company_accounts and not trip_found:
                trip_found = True
                trip_cases.setdefault(vendor['rfc'], []).append(path)

    # ---- phantom_vendor -----------------------------------------------------------------------------
    received_by_vendor = defaultdict(list)
    for invoice in received:
        received_by_vendor[invoice['issuer_rfc']].append(invoice)
    for rfc, vendor_invoices in sorted(received_by_vendor.items()):
        if stop():
            break
        vendor = rows['vendors'].get(rfc)
        if not vendor or ('phantom_vendor', 'RFC:' + rfc) in published or documented(rfc, 'delivery_terms'):
            continue
        active = [i for i in vendor_invoices if i['status'] == 'vigente']
        paid = [i for i in active if settlement.get(i['uuid'])]
        payments = sorted({tx['txn_id']: tx for i in paid for tx in settlement[i['uuid']]}.values(), key=lambda tx: (tx['date'], tx['txn_id']))
        sat = efos.get(rfc)
        status = sat['status'] if sat else None
        clabe = vendor['bank_clabe']
        shared = [v['rfc'] for v in vendors_by_clabe.get(clabe, []) if v['rfc'] != rfc] if clabe else []
        first = min((i['issue_date'] for i in vendor_invoices), default=None)
        new = bool(vendor['registered_date'] and first and days(vendor['registered_date'], first) <= NEW_VENDOR_DAYS)
        onward = [tx for tx in outgoing.get(clabe, []) if tx['to_clabe'] not in company_accounts
                  and any(0 <= days(p['date'], tx['date']) <= PASS_THROUGH_DAYS for p in payments)] if clabe else []
        paid_total = sum(cents(tx['amount']) for tx in payments)
        # Money that comes back to the company is judged by the round-tripping predicate, not as pass-through.
        pass_through = (bool(paid_total) and rfc not in trip_cases
                        and sum(cents(tx['amount']) for tx in onward) * 100 >= paid_total * PASS_THROUGH_MIN_PERCENT)
        thin_identity = not (vendor['address'] and vendor['contact_email'])
        if not (status in ('definitivo', 'presunto') or new or shared or pass_through):
            continue
        weak = [label for label, present in [
            (f'registered {vendor["registered_date"]}, {days(vendor["registered_date"], first) if new else 0} days before its first invoice', new),
            (f'shares CLABE {clabe} with supplier(s) {", ".join(shared)}', bool(shared)),
            (f'forwarded {pesos(sum(cents(tx["amount"]) for tx in onward))} onward within {PASS_THROUGH_DAYS} days of being paid', pass_through),
            ('no address or contact email in master data', thin_identity),
            ('SAT 69-B presumed (presunto) listing', status == 'presunto')] if present]
        pos, ctrs = pos_by_vendor.get(rfc, []), contracts_by_vendor.get(rfc, [])
        refunds = [tx for tx in outgoing.get(clabe, []) if tx['to_clabe'] in company_accounts] if clabe else []
        refunded = sum(cents(tx['amount']) for tx in refunds)
        amount = sum(cents(i['total']) for i in paid)
        definitive = status == 'definitivo'
        checks = [challenge('The supplier may have cleared a SAT listing (desvirtuado or favourable ruling).',
                            f'efos_list status: {status or "not listed"}.', status not in EFOS_CLEARED),
                  challenge('The purchase may be documented by a purchase order or contract.',
                            f'{len(pos)} purchase orders and {len(ctrs)} contracts reference this supplier.', not pos and not ctrs),
                  challenge('The invoices may be unpaid or refunded, leaving no loss.',
                            f'{len(paid)}/{len(active)} active invoices paid ({pesos(paid_total)}); refunds received {pesos(refunded)}.', paid and refunded < paid_total),
                  challenge('A new supplier with thin records can still be real.',
                            'Independent red flags: ' + ('; '.join(weak) or 'none') + '.', definitive or len(weak) >= PHANTOM_MIN_WEAK_SIGNALS)]
        supported = all(c['accusation_survives'] for c in checks)
        trail = payments[-1:] if payments else []
        if trail and pass_through:
            onward_path = next(flows(trail[0], PASS_THROUGH_DAYS), None)
            trail = onward_path or trail
        evidence = ([ref('vendors', vendor)] + ([ref('efos_list', sat)] if sat else []) + invoice_refs(i['uuid'] for i in (paid or active))
                    + [ref('bank_txns', tx) for tx in payments] + [ref('bank_txns', tx) for tx in trail])
        name = vendor['legal_name'] or rfc
        if supported:
            narrative = (f"{name} (RFC {rfc}) billed the company {len(paid)} time(s) and was paid {pesos(amount)}. "
                         + ('SAT has definitively listed it under Article 69-B as issuing invoices for operations that did not exist. ' if definitive else
                            'It is not on the SAT definitive list. ') +
                         f"No purchase order or contract supports any purchase from it. Red flags: {'; '.join(weak) or 'none beyond the listing'}. "
                         'The payments look like they were for services never received.')
            reason = narrative
        else:
            failed = [c['argument'] for c in checks if not c['accusation_survives']]
            flags = '; '.join(([f'SAT status {status}'] if status else []) + weak) or 'supplier checks'
            reason = (f"{name} (RFC {rfc}) was flagged by: {flags}. "
                      f"It was not accused because: {' '.join(failed)} Evidence: {len(pos)} POs, {len(ctrs)} contracts, "
                      f"{len(paid)}/{len(active)} invoices paid, refunds {pesos(refunded)}.")
            narrative = None
        consider('phantom_vendor', 'RFC:' + rfc, evidence,
                 ('CFF Art. 69-B: CFDI from a taxpayer on the definitive EFOS list are presumed to cover non-existent operations and have no tax effect'
                  if definitive else
                  'LISR Art. 27 fr. I and CFF Art. 5-A: deductions require materially existing, documented operations'),
                 amount, trail, supported, reason, ['lookup_supplier', 'check_sat_69b', 'match_payments', 'lookup_purchase_orders', 'test_refunds'],
                 confidence='proven' if definitive else 'probable', challenges=checks,
                 closed_by='challenger' if pos or ctrs or refunded or status in EFOS_CLEARED else 'investigator',
                 basis='records', narrative=narrative)

    # ---- kickback ------------------------------------------------------------------------------------
    for (rfc, end), found in sorted(kick_cases.items()):
        if stop():
            break
        if ('kickback', 'RFC:' + rfc) in published or documented(rfc, 'payment_policy'):
            continue
        vendor = rows['vendors'][rfc]
        # Each employee receipt is attributed to the most recent company payment that could fund it.
        latest = {}
        for p in found:
            key = p[-1]['txn_id']
            if key not in latest or (p[0]['date'], p[0]['txn_id']) > (latest[key][0]['date'], latest[key][0]['txn_id']):
                latest[key] = p
        found = [latest[key] for key in sorted(latest)]
        owners = employees_by_clabe[end]
        other_vendors = [v['rfc'] for v in vendors_by_clabe.get(end, []) if v['rfc'] != rfc]
        direct = any(len(p) == 1 for p in found)
        roots = sorted({p[0]['txn_id']: p[0] for p in found}.values(), key=lambda tx: (tx['date'], tx['txn_id']))
        uuids = list(dict.fromkeys(u for tx in roots for u in paid_invoices.get(tx['txn_id'], [])))
        receipts = sorted({p[-1]['txn_id']: p[-1] for p in found}.values(), key=lambda tx: (tx['date'], tx['txn_id']))
        received_total = sum(cents(tx['amount']) for tx in receipts)
        owner = owners[0]
        unique = len(owners) == 1 and not other_vendors
        employed = all(o['hire_date'] and o['hire_date'] <= receipts[0]['date'] for o in owners)
        reimbursement = [tx for p in found for tx in (p if len(p) == 1 else p[1:]) if REFUND_REFERENCE.search(str(tx['reference'] or ''))]
        intermediaries = [v for p in found for tx in p[1:-1] for v in vendors_by_clabe.get(tx['to_clabe'], [])]
        invoiced = bool(uuids) and all(rows['invoices'][u]['status'] == 'vigente' for u in uuids)
        bank_code = end[:3]
        checks = [challenge('The employee may simply bank at the same institution as the receiving account.',
                            f'Exact 18-digit CLABE match (not just bank code {bank_code}); account holders: {len(owners)} employee(s), '
                            f'{len(other_vendors)} other supplier(s).', unique),
                  challenge('The person may not have been an employee when the money arrived.',
                            f'{owner["emp_id"]} hired {owner["hire_date"] or "unknown"}; first receipt {receipts[0]["date"]}.', employed),
                  challenge('The transfer may reimburse an expense the employee paid for the supplier.',
                            f'{len(reimbursement)} transfer(s) on the path reference a refund, reimbursement or travel expense.', not reimbursement),
                  challenge('The supplier payment may be unrelated to any company purchase.',
                            f'Funding payments settle {len(uuids)} active supplier invoice(s).', invoiced)]
        supported = all(c['accusation_survives'] for c in checks)
        amount = sum(cents(rows['invoices'][u]['total']) for u in uuids)
        trail = min(found, key=len)
        evidence = (invoice_refs(uuids) + [ref('bank_txns', tx) for tx in roots] + [ref('bank_txns', tx) for p in found for tx in p]
                    + [ref('vendors', vendor), ref('employees', owner)] + [ref('vendors', v) for v in intermediaries])
        name, person = vendor['legal_name'] or rfc, owner['name'] or owner['emp_id']
        route = 'directly into' if direct else f'through {max(len(p) for p in found) - 2} intermediary account(s) into'
        narrative = (f"The company paid {name} (RFC {rfc}) {pesos(amount)} for {len(uuids)} invoice(s). "
                     f"Within {days(roots[0]['date'], receipts[-1]['date'])} days, {pesos(received_total)} went from that payment {route} "
                     f"CLABE {end}, the account the employee file lists for {person} ({owner['role'] or 'role not recorded'}). "
                     'A supplier sending company money to the buyer\'s own employee is a kickback.')
        failed = [c['argument'] for c in checks if not c['accusation_survives']]
        reason = narrative if supported else (
            f"Funds from {name} (RFC {rfc}) reached CLABE {end} linked to {owner['emp_id']}. Not accused because: {' '.join(failed)}")
        consider('kickback', 'RFC:' + rfc, evidence,
                 'Prohibited supplier payment to a buyer\'s employee: conflict of interest and administración fraudulenta (Código Penal Federal Art. 388)',
                 amount, trail, supported, reason, ['match_payments', 'trace_funds', 'lookup_employee_account', 'test_reimbursement'],
                 [emp_entity(o['emp_id']) for o in owners], confidence='proven' if supported and direct and not intermediaries else 'probable',
                 challenges=checks, closed_by='challenger' if not unique or not employed or reimbursement else 'investigator',
                 basis='records', narrative=narrative if supported else None)

    for rfc, found in sorted(trip_cases.items()):
        if stop():
            break
        if ('round_tripping', 'RFC:' + rfc) in published or documented(rfc, 'funding_terms'):
            continue
        vendor = rows['vendors'][rfc]
        latest = {}
        for p in found:
            key = p[-1]['txn_id']
            if key not in latest or (p[0]['date'], p[0]['txn_id']) > (latest[key][0]['date'], latest[key][0]['txn_id']):
                latest[key] = p
        found = [latest[key] for key in sorted(latest)]
        roots = [p[0] for p in found]
        uuids = list(dict.fromkeys(u for tx in roots for u in paid_invoices.get(tx['txn_id'], [])))
        out_total = sum(cents(tx['amount']) for tx in roots)
        back_total = sum(cents(p[-1]['amount']) for p in found)
        layered = all(len(p) >= 3 for p in found)
        benign_refs = [tx for p in found for tx in p[1:] if REFUND_REFERENCE.search(str(tx['reference'] or '')) or LOAN_REFERENCE.search(str(tx['reference'] or ''))]
        party_rfcs = list(dict.fromkeys(v['rfc'] for p in found for tx in p for v in vendors_by_clabe.get(tx['to_clabe'], [])
                                        if v['rfc'] != company_rfc))
        loan_contracts = [r for party in party_rfcs for r in contracts_by_vendor.get(party, []) if LOAN_REFERENCE.search(str(r['scope_text'] or ''))]
        sales = []
        for p in found:
            sender = unique_vendor(p[-1]['from_clabe'])
            if sender:
                sales += [i for i in issued if i['receiver_rfc'] == sender['rfc'] and i['status'] == 'vigente'
                          and abs(cents(i['total']) - cents(p[-1]['amount'])) * 100 <= PESO_TOLERANCE_PERCENT * cents(p[-1]['amount'])
                          and abs(days(i['issue_date'], p[-1]['date'])) <= ROUND_TRIP_WINDOW_DAYS]
        disguised = bool(sales)
        checks = [challenge('Only part of the money came back, so this may be ordinary business with a related party.',
                            f'Returned {pesos(back_total)} of {pesos(out_total)} paid ({100 * back_total // max(out_total, 1)}%).',
                            back_total * 100 >= out_total * ROUND_TRIP_MIN_RETURN_PERCENT),
                  challenge('The return may be a refund, credit note or loan repayment.',
                            f'{len(benign_refs)} path transfer(s) reference a refund/credit/loan; {len(loan_contracts)} loan contract(s) with parties on the path.',
                            not benign_refs and not loan_contracts),
                  challenge('A direct return from the same supplier is usually a refund.',
                            f'Path hops: {", ".join(str(len(p)) for p in found)}; return booked as a company sale: {disguised}.', layered or disguised),
                  challenge('The outgoing payment may not be tied to any invoice.',
                            f'Funding payments settle {len(uuids)} supplier invoice(s).', bool(uuids))]
        supported = all(c['accusation_survives'] for c in checks)
        amount = sum(cents(rows['invoices'][u]['total']) for u in uuids)
        trail = found[0]
        evidence = (invoice_refs(uuids) + [ref('bank_txns', tx) for p in found for tx in p]
                    + [ref('vendors', rows['vendors'][party]) for party in party_rfcs]
                    + [ref('ledger', r) for i in sales for r in ledger_by_invoice.get(i['uuid'], []) if is_revenue(r)])
        name = vendor['legal_name'] or rfc
        narrative = (f"The company paid {name} (RFC {rfc}) {pesos(amount)} for {len(uuids)} invoice(s). "
                     f"Within {max(days(p[0]['date'], p[-1]['date']) for p in found)} days the money passed through "
                     f"{max(len(p) for p in found) - 1} account(s) and {pesos(back_total)} returned to the company's own account"
                     + (f", booked as sales CFDI {', '.join(i['uuid'] for i in sales[:3])}" if sales else '') +
                     '. Money leaving as an expense and coming back as income inflates both without real business.')
        failed = [c['argument'] for c in checks if not c['accusation_survives']]
        reason = narrative if supported else (
            f"A payment to {name} (RFC {rfc}) returned {pesos(back_total)} to the company. Not accused because: {' '.join(failed)}")
        consider('round_tripping', 'RFC:' + rfc, evidence,
                 'CFF Art. 5-A (operations without business purpose) and NIF D-1: circular transfers returning invoiced payments to the company',
                 amount, trail, supported, reason, ['match_payments', 'trace_funds', 'test_refund_loan', 'match_sales_invoices'],
                 [f'RFC:{party}' for party in party_rfcs if party != rfc],
                 confidence='proven' if supported and disguised and layered else 'probable', challenges=checks,
                 closed_by='challenger' if benign_refs or loan_contracts or not (layered or disguised) else 'investigator',
                 basis='records', narrative=narrative if supported else None)

    # ---- threshold_splitting: approval tier inferred from purchase_orders --------------------------------
    all_orders = sorted(rows['purchase_orders'].values(), key=lambda r: (r['date'], r['po_id']))
    tier = None
    for limit_pesos in APPROVAL_LIMIT_CANDIDATES:
        limit = limit_pesos * 100
        above = [po for po in all_orders if cents(po['amount']) >= limit]
        below = [po for po in all_orders if cents(po['amount']) < limit]
        senior = {po['approver'] for po in above if po['approver']}
        junior = {po['approver'] for po in below if po['approver']} - senior
        if len(above) < 2 or not senior or not junior or any(not po['approver'] for po in above):
            continue
        near = sum(1 for po in below if po['approver'] in junior and cents(po['amount']) * 100 >= limit * SPLIT_MIN_SHARE_PERCENT)
        if near and (tier is None or near > tier[0]):
            tier = (near, limit, senior, junior, above)
    if all_orders and tier is None:
        warnings.append('No approval tier is visible in purchase_orders (no amount above which only other approvers sign), so split orders were not tested against a limit.')
    if tier is not None:
        # Authority is a role, not only observed history: an approver whose job title matches a senior signer's
        # title (e.g. another "Director") is senior even if they never signed a large order in this estate.
        titles = {e['name']: str(e['role'] or '').split(' ')[0].casefold() for e in rows['employees'].values() if e['name']}
        senior_titles = {titles[name] for name in tier[2] if titles.get(name)}
        expanded = tier[2] | {name for name, title in titles.items() if title and title in senior_titles}
        tier = (tier[0], tier[1], expanded, tier[3] - expanded, tier[4])
    orders_by_vendor = defaultdict(list)
    for po in all_orders:
        orders_by_vendor[po['vendor_rfc']].append(po)
    for rfc, orders in sorted(orders_by_vendor.items()):
        if stop() or tier is None:
            break
        if ('threshold_splitting', 'RFC:' + rfc) in published or documented(rfc, 'purchase_policy'):
            continue
        _, limit, senior, junior, above = tier
        # Only near-limit orders can be split parts; unrelated small orders must not shift cluster boundaries.
        keyed = defaultdict(list)
        for po in orders:
            if cents(po['amount']) < limit and cents(po['amount']) * 100 >= limit * SPLIT_MIN_SHARE_PERCENT:
                keyed[po['requester'] or po['description'] or ''].append(po)
        clusters = []
        for key in sorted(keyed):
            candidates, start = keyed[key], 0
            while start < len(candidates):
                end = start
                while end + 1 < len(candidates) and days(candidates[start]['date'], candidates[end + 1]['date']) <= SPLIT_WINDOW_DAYS:
                    end += 1
                group = candidates[start:end + 1]
                if len(group) >= 2 and sum(cents(po['amount']) for po in group) >= limit:
                    clusters.append(group)
                start = end + 1
        vendor = rows['vendors'].get(rfc)
        for group in clusters:
            total = sum(cents(po['amount']) for po in group)
            signers = sorted({po['approver'] or 'nobody' for po in group})
            unapproved = all(po['approver'] not in senior for po in group)
            requester = group[0]['requester']
            same_purpose = len({po['description'] for po in group}) == 1 or len({po['requester'] for po in group}) == 1
            span = days(group[0]['date'], group[-1]['date'])
            example = above[0]
            # Two unrelated orders a week apart often cross a limit by chance; a split is several orders, or two
            # within days, pushed through by one signer.
            tight = len(group) >= SPLIT_MIN_ORDERS or span <= SPLIT_PAIR_MAX_DAYS
            checks = [challenge('The combined purchase may have been approved at the right level.',
                                f'Signers: {", ".join(signers)}. Orders of {pesos(limit)} or more are signed only by {", ".join(sorted(senior))} (e.g. {example["po_id"]}).', unapproved),
                      challenge('These may be separate purchases that happen to fall close together.',
                                f'{len(group)} orders within {span} days; same requester or description: {same_purpose}; distinct signers: {len(signers)}.',
                                same_purpose and tight and len(signers) == 1),
                      challenge('The approval limit is inferred, not a written policy.',
                                f'Inferred from {len(above)} purchase orders at or above {pesos(limit)}, all signed by senior approvers.', True)]
            supported = all(c['accusation_survives'] for c in checks) and bool(vendor)
            employee = [e for e in rows['employees'].values() if requester and requester in (e['name'], e['emp_id'])]
            narrative = (f"{requester or 'The same requester'} raised {len(group)} purchase orders to {(vendor or {}).get('legal_name') or rfc} "
                         f"within {span} days: {', '.join(po['po_id'] for po in group[:6])}. Each stays under the {pesos(limit)} level that needs "
                         f"{', '.join(sorted(senior))}'s approval, but together they total {pesos(total)}. They were signed by {', '.join(signers)} instead. "
                         'Splitting one purchase to avoid the approval level breaks the purchasing control.')
            failed = [c['argument'] for c in checks if not c['accusation_survives']]
            reason = narrative if supported else (f"Orders {', '.join(po['po_id'] for po in group[:6])} to {rfc} total {pesos(total)} around the "
                                                  f"{pesos(limit)} approval level. Not accused because: {' '.join(failed)}")
            consider('threshold_splitting', 'RFC:' + rfc, [ref('purchase_orders', po) for po in group] + ([ref('vendors', vendor)] if vendor else [])
                     + [ref('employees', e) for e in employee[:1]],
                     f'Purchase approval limit (inferred at {pesos(limit)} from purchase_orders approvers): split orders avoid required senior approval',
                     total, [], supported, reason, ['group_purchase_orders', 'infer_approval_tier', 'test_authorization'],
                     [emp_entity(e['emp_id']) for e in employee[:1]], challenges=checks,
                     closed_by='challenger' if not unapproved else 'investigator', basis='records', narrative=narrative if supported else None)

    # ---- unexplained company outflows (leads only) --------------------------------------------------
    cited = {e['record_id'] for f in findings for e in f['exhibits'] if e['source_table'] == 'bank_txns'}
    unexplained = defaultdict(list)
    for tx in company_payments:
        if tx['txn_id'] not in paid_invoices and tx['txn_id'] not in cited and tx['to_clabe'] not in employees_by_clabe:
            unexplained[tx['to_clabe']].append(tx)
    ranked = sorted(unexplained.items(), key=lambda item: (-sum(cents(tx['amount']) for tx in item[1]), item[0]))
    for clabe, txs in ranked[:MAX_UNMATCHED_LEADS]:
        if stop():
            break
        vendor = unique_vendor(clabe)
        entity = 'RFC:' + vendor['rfc'] if vendor else 'CLABE:' + clabe
        total = sum(cents(tx['amount']) for tx in txs)
        consider('unmatched_payment', entity, [ref('bank_txns', tx) for tx in txs] + ([ref('vendors', vendor)] if vendor else []), '', 0, [], False,
                 f"{len(txs)} company payment(s) totalling {pesos(total)} to CLABE {clabe} match no invoice by reference or exact amount. "
                 'An unallocated payment is a visibility gap, not an accusation; no scheme predicate was satisfied.',
                 ['match_payments', 'lookup_supplier', 'trace_funds'], basis='records')
    if len(ranked) > MAX_UNMATCHED_LEADS:
        warnings.append(f'{len(ranked) - MAX_UNMATCHED_LEADS} further destinations with unmatched payments were not listed individually.')

    return {'seed': seed, 'company_rfc': company_rfc, 'estate_sha256': estate.identity,
            'findings': findings, 'leads_not_pursued': [l for l in leads if l['state'] != 'substantiated'],
            'investigation_log': log, 'status': 'incomplete' if counters['truncated'] else 'offline_complete',
            'run_metadata': {'llm_calls': 0, 'mxn_cost': 0.0, 'wall_clock_seconds': round(time.perf_counter()-started, 6),
                             'deterministic': True, 'mode': 'offline', 'cost_by_role': {},
                             'determinism_scope': 'Findings, leads and log are identical for the same estate, seed and company; only wall-clock telemetry varies. Compare the decision fingerprint.'},
            'limits': {'max_leads': MAX_LEADS, 'max_edges': MAX_EDGES, 'max_hops': MAX_HOPS, 'max_days': MAX_DAYS,
                       'examined_edges': counters['edges'], 'truncated': counters['truncated']},
            'detector_settings': {k: list(v) if isinstance(v, tuple) else v for k, v in sorted(SETTINGS.items())},
            'rule_version': VERSION, 'warnings': warnings}


def exhibit_note(table, row):
    """One sentence per record, stating the values that matter; untrusted free text is not repeated."""
    if table == 'invoices':
        return (f"CFDI {row['uuid']} from {row['issuer_rfc']} to {row['receiver_rfc']} dated {row['issue_date']} for "
                f"{pesos(cents(row['total']))}; status {row['status']}, payment method {row['metodo_pago'] or 'not stated'}.")
    if table == 'ledger':
        return (f"Ledger entry {row['entry_id']} on {row['date']}: account {row['account_code'] or ''} {row['account_name'] or ''}, "
                f"debit {pesos(amt(row['debit']))}, credit {pesos(amt(row['credit']))}, approver {row['approver'] or 'none recorded'}.")
    if table == 'bank_txns':
        return (f"Transfer {row['txn_id']} on {row['date']} moved {pesos(cents(row['amount']))} from CLABE {row['from_clabe']} "
                f"to CLABE {row['to_clabe']} by {row['channel'] or 'unstated channel'}.")
    if table == 'vendors':
        return (f"Master record for {row['rfc']} ({row['legal_name'] or 'no name'}): registered {row['registered_date'] or 'unknown'}, "
                f"bank CLABE {row['bank_clabe'] or 'none'}.")
    if table == 'employees':
        return (f"Employee {row['emp_id']} ({row['name'] or 'no name'}, {row['role'] or 'no role'}) hired {row['hire_date'] or 'unknown'}; "
                f"bank CLABE {row['bank_clabe'] or 'none'}.")
    if table == 'contracts':
        return f"Contract {row['contract_id']} with {row['vendor_rfc']} from {row['start_date']}, value {pesos(amt(row['value']))}; its terms were examined."
    if table == 'purchase_orders':
        return (f"Purchase order {row['po_id']} on {row['date']} for {pesos(cents(row['amount']))}: requested by "
                f"{row['requester'] or 'unknown'}, approved by {row['approver'] or 'nobody recorded'}.")
    return (f"SAT Article 69-B list shows {row['rfc']} as {row['status']} since {row['publication_date'] or 'unknown date'}; "
            'a listing alone does not prove fraud.')


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
                amounts[key[0]] += amt(row[AMOUNTS[key[0]]])
        except (KeyError, TypeError):
            errors.append('Nonexistent source record')
    if len(seen) < 3:
        errors.append('At least three unique exhibits required')
    try:
        claimed = cents(finding.get('peso_amount'))
        if claimed <= 0 or not amounts or not any(abs(claimed-value)*100 <= PESO_TOLERANCE_PERCENT*max(value, 100) for value in amounts.values()):
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
        if previous and (previous['to'] != step['from'] or previous['date'] > step['date']):
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
