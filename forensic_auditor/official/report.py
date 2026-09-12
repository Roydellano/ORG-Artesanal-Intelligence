"""Standalone, escaped case files and self-contained offline replay archives."""
from collections import defaultdict
from copy import deepcopy
import hashlib
import html
import io
import json
import zipfile

from .audit import investigate, validate_finding, VERSION
from .estate import AMOUNTS, cents, load, money

LIMITATIONS = [
    'Findings establish narrow discrepancies in supplied records, not legal guilt, authenticity or intent. All accusations are probable.',
    'Missing ownership, invoice links, approval rules, delivery attestations or commercial purpose cause abstention. SAT matches and cycles alone are insufficient.',
    'Contract facts may use the documented typed JSON convention. Unrecognized prose is retained as evidence but cannot independently satisfy a rule.',
    'Revenue account names currently recognized: Ingresos, Revenue, Ventas and Sales revenue. Other charts require an explicit adapter.',
    'Discovery is bounded to 128 leads, 10,000 bank edges, four hops and 30 days. An exhausted budget marks the run incomplete.',
    'MXN is the estate format currency. No currency conversion or tax-liability calculation is performed.',
    'Exposure categories overlap. Shared invoice and purchase-order amounts are counted once in the summary; employee receipts and each bank hop are not added again.',
]


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)


def validate_publication(estate, case):
    """Re-run predicates against source bytes, not user-editable serialized flags."""
    if case.get('estate_sha256') != estate.identity or case.get('rule_version') != VERSION:
        raise ValueError('Estate identity or rule version does not match the run')
    original = load(estate.content)
    if original.identity != estate.identity:
        raise ValueError('Source bytes changed')
    trusted = investigate(original, case['seed'], case['company_rfc'])
    allowed = {canonical(f) for f in trusted['findings']}
    for finding in case['findings']:
        if canonical(finding) not in allowed or validate_finding(original, finding):
            raise ValueError('Finding failed source predicate revalidation')
    if case['run_metadata']['mode'] == 'offline' and case['status'] == 'offline_complete':
        for key in ('findings', 'leads_not_pursued', 'investigation_log'):
            if case[key] != trusted[key]:
                raise ValueError('Saved decisions do not match source predicate review')


def exposure(case):
    """Deduplicate the amount basis, never the sum of all money trail hops."""
    amounts = {}
    for f in case['findings']:
        if f['scheme_type'] == 'threshold_splitting':
            # Groups cannot overlap in discovery; identify their exact source set.
            key = tuple(sorted(e['record_id'] for e in f['exhibits'] if e['source_table'] == 'purchase_orders'))
            amounts[('orders', key)] = cents(f['peso_amount'])
        else:
            key = tuple(sorted(e['record_id'] for e in f['exhibits'] if e['source_table'] == 'invoices'))
            amounts[('invoice', key)] = max(amounts.get(('invoice', key), 0), cents(f['peso_amount']))
    return sum(amounts.values())


def masked(estate, case):
    """Deterministic dataset-local aliases; no source prose included in masked view."""
    result = deepcopy(case)
    mapping = {}
    def alias(value):
        return 'Record-' + hashlib.sha256((estate.identity + ':' + str(value)).encode()).hexdigest()[:12]
    for table, rows in estate.rows.items():
        for rid, row in rows.items():
            mapping[rid] = alias(rid)
            for key, value in row.items():
                if key in ('rfc', 'issuer_rfc', 'receiver_rfc', 'vendor_rfc', 'emp_id', 'name', 'legal_name', 'bank_clabe', 'from_clabe', 'to_clabe', 'requester', 'approver') and value:
                    mapping[str(value)] = alias(value)
    import re
    patterns = [re.escape(key) for key in sorted(mapping, key=len, reverse=True) if len(key) >= 4]
    pattern = re.compile(r'(?<![\w-])(?:' + '|'.join(patterns) + r')(?![\w-])') if patterns else None
    def walk(value, key=''):
        if key == 'fx_source':
            return '[Supplied exchange-rate source; reveal locally]'
        if isinstance(value, dict):
            return {k: walk(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [walk(v, key) for v in value]
        if isinstance(value, str) and pattern:
            if key == 'record_id' and value in mapping:
                return mapping[value]
            return pattern.sub(lambda match: mapping[match.group()], value)
        return value
    return walk(result)


def diagram(finding, amount_by_exhibit):
    esc = html.escape
    steps = finding['money_trail']
    if not steps:
        # Noncash findings still receive a rendered, exhibit-linked accounting trail.
        relevant = [ex for ex in finding['exhibits'] if ex['source_table'] in ('invoices', 'ledger', 'purchase_orders')]
        steps = [{'from': ex['source_table'], 'to': ex['record_id'], 'amount': amount_by_exhibit[ex['exhibit_id']],
                  'date': 'recorded exposure', 'exhibit_id': ex['exhibit_id']} for ex in relevant]
        label = 'Accounting/approval evidence diagram; no cash movement inferred'
    else:
        label = 'Observed money trail; arrows do not prove identical pesos through commingling'
    height = max(100, len(steps)*94)
    parts = [f'<svg role="img" aria-label="{esc(label)}" viewBox="0 0 850 {height}" xmlns="http://www.w3.org/2000/svg">',
             '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#286749"/></marker></defs>']
    for i, step in enumerate(steps):
        y = i*94+15
        parts.append(f'<rect x="5" y="{y}" width="260" height="42" rx="7" fill="#e7eee9"/><rect x="580" y="{y}" width="260" height="42" rx="7" fill="#e7eee9"/>')
        parts.append(f'<text x="15" y="{y+26}" font-size="12">{esc(str(step["from"])[:34])}</text><text x="590" y="{y+26}" font-size="12">{esc(str(step["to"])[:34])}</text>')
        parts.append(f'<path d="M270,{y+21} H570" stroke="#286749" stroke-width="2" marker-end="url(#arrow)"/>')
        parts.append(f'<text x="285" y="{y+13}" font-size="12">MXN {step["amount"]:,.2f} · {esc(step["date"])}</text>')
        parts.append(f'<a href="#{esc(step["exhibit_id"], quote=True)}"><text x="285" y="{y+48}" font-size="12">{esc(step["exhibit_id"])}</text></a>')
    return f'<p>{label}</p>' + ''.join(parts) + '</svg>'


def render(estate, original, *, reveal=False):
    case = original if reveal else masked(estate, original)
    esc = html.escape
    vendor = estate.rows['vendors'].get(original['company_rfc'], {})
    company = vendor.get('legal_name') or original['company_rfc']
    if not reveal:
        company = 'Masked company'
    dates = sorted(r['issue_date'] for r in estate.rows['invoices'].values() if r['issue_date'])
    period = f'{dates[0]} — {dates[-1]}' if dates else 'No invoice period supplied'
    meta = case['run_metadata']
    cost_text = f'{meta["mxn_cost"]:.4f}' if meta['mxn_cost'] is not None else 'unavailable (incomplete billing evidence)'
    parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Forensic case file</title>',
             '<style>body{font:16px/1.55 system-ui;color:#203c31;max-width:1040px;margin:40px auto;padding:0 24px}h1{font-size:36px}h2{border-top:2px solid #adc3b4;padding-top:24px}table{border-collapse:collapse;width:100%;margin:18px 0}td,th{border-bottom:1px solid #ced9d1;padding:9px;text-align:left;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}svg{width:100%;height:auto}a{color:#206846}article{break-inside:avoid}small{color:#58675e}@media print{body{margin:0}h2{break-after:avoid}}</style></head><body>',
             f'<h1>{esc(company)} — forensic case file</h1><p>Audit period: {esc(period)} · Estate seed: {case["seed"]}</p>',
             f'<p>{esc(case["status"])} · {esc(meta["mode"])} · {"Original local judge export" if reveal else "Masked review"}</p>',
             f'<p>LLM calls: {meta["llm_calls"]} · MXN cost: {cost_text} · Wall-clock seconds: {meta["wall_clock_seconds"]:.6f}</p>',
             f'<p>Deterministic: {meta["deterministic"]}. {esc(meta["determinism_scope"])}</p>',
             '<h2>Executive summary</h2>',
             f'<p>The supplied records support {len(case["findings"])} narrow probable findings. {len(case["leads_not_pursued"])} leads were closed without accusation. '
             'These conclusions depend on the supplied records and their stated limitations.</p>',
             f'<table><tr><th>Findings and confidence</th><td>{len(case["findings"])} probable; 0 proven</td></tr><tr><th>Total exposure</th><td>MXN {money(exposure(original)):,.2f}</td></tr>'
             f'<tr><th>Leads investigated and closed without accusation</th><td>{len(case["leads_not_pursued"])}</td></tr></table>',
             '<p>Total exposure deduplicates shared invoice bases and order groups. It combines accounting exposure categories, not cash loss; bank hops and employee receipts are not added.</p>']
    for f, raw in zip(case['findings'], original['findings']):
        amount_by_exhibit = {}
        for ex in raw['exhibits']:
            row = estate.row(ex['source_table'], ex['record_id'])
            if ex['source_table'] in AMOUNTS:
                value = row[AMOUNTS[ex['source_table']]]
            elif ex['source_table'] == 'ledger':
                value = money(max(cents(row['debit']), cents(row['credit'])))
            else:
                value = 0
            amount_by_exhibit[ex['exhibit_id']] = value
        entity = f['entities'][0]
        raw_entity = raw['entities'][0]
        name = estate.rows['vendors'].get(raw_entity.removeprefix('RFC:'), {}).get('legal_name', raw_entity) if reveal else entity
        parts += [f'<article><h2>{esc(name)} · {esc(entity)} · {esc(f["scheme_type"])}</h2>',
                  f'<p><b>Rule broken:</b> {esc(f["rule_broken"])}</p>',
                  f'<p><b>Amount and confidence:</b> MXN {f["peso_amount"]:,.2f} · {esc(f["confidence"])}</p>',
                  f'<h3>What happened</h3><p>{esc(f["narrative"])}</p><h3>Money trail</h3>{diagram(f, amount_by_exhibit)}',
                  '<h3>Exhibits</h3><table><tr><th>Exhibit</th><th>Source table</th><th>Record ID</th><th>What it supports</th></tr>']
        sums = defaultdict(int)
        addends = defaultdict(list)
        for ex, raw_ex in zip(f['exhibits'], raw['exhibits']):
            parts.append(f'<tr id="{esc(ex["exhibit_id"], quote=True)}"><td>{esc(ex["exhibit_id"])}</td><td>{esc(ex["source_table"])}</td><td>{esc(ex["record_id"])}</td><td>{esc(ex["note"])}</td></tr>')
            if raw_ex['source_table'] in AMOUNTS:
                value = cents(estate.row(raw_ex['source_table'], raw_ex['record_id'])[AMOUNTS[raw_ex['source_table']]])
                sums[raw_ex['source_table']] += value
                addends[raw_ex['source_table']].append(f'{ex["exhibit_id"]} ({money(value):,.2f})')
        parts += ['</table><h3>Reconciliation</h3>', '<p>' + ' ; '.join(f'{esc(t)}: {esc(" + ".join(addends[t]))} = MXN {money(v):,.2f}' for t, v in sums.items()) +
                  f'. Claimed = MXN {f["peso_amount"]:,.2f}. Tables are checked separately within 2%; invoice and settlement are not added.</p>',
                  '<p>Alternative review: refunds, reversals, ownership ambiguity and supplied permissions were checked by the applicable rule. Publication was independently revalidated against original source records.</p></article>']
    parts.append('<h2>Leads not pursued</h2>')
    for lead in case['leads_not_pursued']:
        entity_name = estate.rows['vendors'].get(lead['entity'].removeprefix('RFC:'), {}).get('legal_name', lead['entity']) if reveal else lead['entity']
        parts.append(f'<article><h3>{esc(entity_name)} · {esc(lead["entity"])} · {esc(lead["signal"])}</h3><p>{esc(lead["reason"])}</p>'
                     f'<p>Evidence examined: {esc(", ".join(lead["evidence_examined"]))}</p><p>Tools: {esc(", ".join(lead["tool_calls_made"]))} · Closed by: {esc(lead["closed_by"])}</p></article>')
    parts += ['<h2>Method and limits</h2><p>A bounded local controller forms leads, retrieves source records, checks contractual and accounting predicates, tests alternatives, and validates citations and arithmetic before publication. No uploaded text is executed.</p>',
              '<ul>' + ''.join(f'<li>{esc(item)}</li>' for item in [*LIMITATIONS, *case.get('warnings', [])]) + '</ul>',
              f'<p>Estate SHA-256: {esc(original["estate_sha256"])} · Rule version: {VERSION}</p>',
              '<p>Reproduce with the same estate, seed and company RFC using python -m forensic_auditor.official run. To reproduce this completed artifact with no network or model calls, use python -m forensic_auditor.official replay RUN.replay.zip --output replay. Original telemetry is retained in replay.</p>',
              '<h3>Decision log</h3><pre>' + esc(canonical(case['investigation_log'])) + '</pre>']
    if case.get('ai_events'):
        parts.append('<h3>AI tool actions</h3><pre>' + esc(canonical(case['ai_events'])) + '</pre>')
    if reveal:
        refs = sorted({(e['source_table'], e['record_id']) for f in original['findings'] for e in f['exhibits']})
        parts.append('<h3>Original source records</h3>')
        for table, rid in refs:
            parts.append('<pre>' + esc(canonical(estate.evidence(table, rid))) + '</pre>')
    return ''.join(parts) + '</body></html>'


def bundle(estate, case):
    validate_publication(estate, case)
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, content in [('estate.db', estate.content), ('submission.json', canonical(case).encode())]:
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            archive.writestr(info, content)
    return output.getvalue()


def replay(content):
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        if sorted(archive.namelist()) != ['estate.db', 'submission.json'] or sum(i.file_size for i in archive.infolist()) > 40_000_000:
            raise ValueError('Invalid replay archive')
        estate = load(archive.read('estate.db'))
        case = json.loads(archive.read('submission.json'))
    validate_publication(estate, case)
    return estate, case


def answer(case, question):
    """Read saved decisions; questions never cross the inference boundary."""
    lowered = question.casefold()
    matching = [lead for lead in case['leads_not_pursued'] if lead['entity'].casefold() in lowered or lead['lead_id'].casefold() in lowered]
    if matching:
        return {'answer': '\n'.join(l['reason'] for l in matching), 'evidence': [e for l in matching for e in l['evidence_examined']]}
    matching_f = [f for f in case['findings'] if any(entity.casefold() in lowered for entity in f['entities']) or f['lead_id'].casefold() in lowered]
    if not matching_f and any(word in lowered for word in ('confidence', 'finding', 'evidence', 'amount', 'confianza', 'monto')):
        matching_f = case['findings']
    if matching_f:
        return {'answer': '\n'.join(f'{f["lead_id"]}: {f["confidence"]}; MXN {f["peso_amount"]:.2f}. {f["narrative"]}' for f in matching_f),
                'evidence': [f'{e["source_table"]}:{e["record_id"]}' for f in matching_f for e in f['exhibits']]}
    if any(word in lowered for word in ('total', 'cost', 'time')):
        return {'answer': f'Deduplicated exposure MXN {money(exposure(case)):.2f}. Run metadata: {canonical(case["run_metadata"])}', 'evidence': []}
    return {'answer': 'The saved case does not establish that answer. Ask about a listed entity, lead ID, findings, confidence or totals. No investigation was rerun.', 'evidence': []}
