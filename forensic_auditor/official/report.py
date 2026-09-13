"""Standalone, escaped case files and self-contained offline replay archives."""
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import html
import io
import json
import re
import zipfile

from .audit import investigate, validate_finding, amt, VERSION
from .estate import AMOUNTS, cents, load, money

LIMITATIONS = [
    'Findings establish discrepancies in the supplied records, not legal guilt, document authenticity or intent. '
    '"Proven" means the rule breach is fully shown by the cited records; "probable" means a corroborated pattern with an inferred element.',
    'Detectors only open leads. SAT 69-B matches, cycles, new suppliers and unpaid sales never publish on their own; each needs corroboration and must survive every challenger argument.',
    'Thresholds (windows, return shares, approval-limit candidates) are constants in forensic_auditor/official/audit.py and are listed in the JSON detector_settings.',
    'Approval limits are inferred from who signs purchase orders above each candidate amount. Estates with no visible approval tier are not tested for split purchases.',
    'Revenue accounts are recognized by name (Ingresos, Revenue, Ventas, Sales revenue) or SAT grouping code 4xx; expenses by name or codes 5xx/6xx. Other charts need an adapter.',
    'Uncollected-sale tests run only when at least half of active sales show a collection; otherwise the estate is treated as not modelling collections.',
    'Account ownership is exact 18-digit CLABE equality. Shared bank codes, cash movements outside bank_txns, and accounts not in master data are invisible.',
    'Discovery is bounded to 400 leads, 200,000 bank edges and four hops. An exhausted budget marks the run incomplete.',
    'Exposure categories overlap. Shared invoice and purchase-order bases are counted once in the summary; employee receipts and each bank hop are not added again.',
]

CANNOT_DETECT = [
    'Collusion fully documented with purchase orders, contracts and genuine-looking collections.',
    'Kickbacks paid in cash, to relatives, or to accounts absent from the employee file.',
    'Price inflation on real deliveries (overbilling) without a split, cycle or listing signal.',
    'Schemes spanning periods or entities outside the supplied estate.',
]

OUT_OF_SCOPE = [
    'CFDI XML signature/authenticity verification and live SAT list lookups (the supplied efos_list is used as-is).',
    'Tax liability calculation, currency conversion and legal determinations.',
    'Natural-language interpretation of contract prose; only the optional typed JSON convention is read as terms.',
]


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)


def fingerprint(case):
    """Hash of every decision (findings, leads, log). Equal fingerprints mean identical conclusions."""
    decisions = {key: case[key] for key in ('findings', 'leads_not_pursued', 'investigation_log')}
    return hashlib.sha256(canonical(decisions).encode()).hexdigest()[:16]


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


def diagram(finding, amount_by_exhibit, parallel=()):
    """Money trail as SVG. ``parallel`` holds further cited transfers (e.g. repeated payments) drawn below the trail."""
    esc = html.escape
    steps = list(finding['money_trail'])
    if not steps and not parallel:
        # Noncash findings still receive a rendered, exhibit-linked accounting trail.
        relevant = [ex for ex in finding['exhibits'] if ex['source_table'] in ('invoices', 'ledger', 'purchase_orders')]
        steps = [{'from': ex['source_table'], 'to': ex['record_id'], 'amount': amount_by_exhibit[ex['exhibit_id']],
                  'date': 'recorded exposure', 'exhibit_id': ex['exhibit_id']} for ex in relevant]
        label = 'Accounting/approval evidence diagram; no cash movement inferred'
    else:
        label = 'Observed money trail (top), then other cited transfers; arrows do not prove identical pesos through commingling'
    rows = [(step, 'trail') for step in steps] + [(step, 'other') for step in parallel]
    height = max(100, len(rows)*94)
    parts = [f'<svg role="img" aria-label="{esc(label)}" viewBox="0 0 850 {height}" xmlns="http://www.w3.org/2000/svg">',
             '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#286749"/></marker></defs>']
    for i, (step, kind) in enumerate(rows):
        y = i*94+15
        fill = '#e7eee9' if kind == 'trail' else '#f1f1ec'
        dash = '' if kind == 'trail' else ' stroke-dasharray="6 4"'
        parts.append(f'<rect x="5" y="{y}" width="260" height="42" rx="7" fill="{fill}"/><rect x="580" y="{y}" width="260" height="42" rx="7" fill="{fill}"/>')
        parts.append(f'<text x="15" y="{y+26}" font-size="12">{esc(str(step["from"])[:34])}</text><text x="590" y="{y+26}" font-size="12">{esc(str(step["to"])[:34])}</text>')
        parts.append(f'<path d="M270,{y+21} H570" stroke="#286749" stroke-width="2"{dash} marker-end="url(#arrow)"/>')
        parts.append(f'<text x="285" y="{y+13}" font-size="12">MXN {float(step["amount"]):,.2f} · {esc(str(step["date"]))}</text>')
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
    confidence = Counter(f['confidence'] for f in case['findings'])
    schemes = Counter(f['scheme_type'].replace('_', ' ') for f in case['findings'])
    summary = ('No accusation met the evidence standard. ' if not case['findings'] else
               'The records support ' + ', '.join(f'{n} {name}' for name, n in sorted(schemes.items())) + ' finding(s). ')
    parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Forensic case file</title>',
             '<style>body{font:16px/1.55 system-ui;color:#203c31;max-width:1040px;margin:40px auto;padding:0 24px}h1{font-size:36px}h2{border-top:2px solid #adc3b4;padding-top:24px}table{border-collapse:collapse;width:100%;margin:18px 0}td,th{border-bottom:1px solid #ced9d1;padding:9px;text-align:left;overflow-wrap:anywhere;vertical-align:top}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}svg{width:100%;height:auto}a{color:#206846}article{break-inside:avoid}small{color:#58675e}.held{color:#206846;font-weight:600}.broke{color:#8a3b12;font-weight:600}@media print{body{margin:0}h2{break-after:avoid}}</style></head><body>',
             f'<h1>{esc(company)} — forensic case file</h1><p>Audit period: {esc(period)} · Estate seed: {case["seed"]}</p>',
             f'<p>{esc(case["status"])} · {esc(meta["mode"])} · {"Original local judge export" if reveal else "Masked review"}</p>',
             f'<p>LLM calls: {meta["llm_calls"]} · MXN cost: {cost_text} · Wall-clock seconds: {meta["wall_clock_seconds"]:.6f}</p>',
             f'<p>Deterministic: {meta["deterministic"]}. {esc(meta["determinism_scope"])} Decision fingerprint: <code>{fingerprint(original)}</code></p>',
             '<h2>Executive summary</h2>',
             f'<p>{esc(summary)}{len(case["leads_not_pursued"])} other leads were investigated and closed without accusation, each with its reason below. '
             'These conclusions depend on the supplied records and their stated limitations.</p>',
             f'<table><tr><th>Findings and confidence</th><td>{len(case["findings"])} total: {confidence["proven"]} proven, {confidence["probable"]} probable</td></tr><tr><th>Total exposure</th><td>MXN {money(exposure(original)):,.2f}</td></tr>'
             f'<tr><th>Leads investigated and closed</th><td>{len(case["leads_not_pursued"])}</td></tr></table>',
             '<p>Total exposure deduplicates shared invoice bases and order groups. It combines accounting exposure categories, not cash loss; bank hops and employee receipts are not added.</p>']
    for f, raw in zip(case['findings'], original['findings']):
        amount_by_exhibit = {}
        for ex in raw['exhibits']:
            row = estate.row(ex['source_table'], ex['record_id'])
            if ex['source_table'] in AMOUNTS:
                value = money(amt(row[AMOUNTS[ex['source_table']]]))
            elif ex['source_table'] == 'ledger':
                value = money(max(amt(row['debit']), amt(row['credit'])))
            else:
                value = 0
            amount_by_exhibit[ex['exhibit_id']] = value
        in_trail = {step['exhibit_id'] for step in raw['money_trail']}
        parallel = []
        for ex in raw['exhibits']:
            if ex['source_table'] == 'bank_txns' and ex['exhibit_id'] not in in_trail:
                tx = estate.row('bank_txns', ex['record_id'])
                parallel.append({'from': tx['from_clabe'], 'to': tx['to_clabe'], 'amount': tx['amount'], 'date': tx['date'], 'exhibit_id': ex['exhibit_id']})
        if not reveal:
            parallel = masked(estate, {'steps': parallel})['steps']
        entity = f['entities'][0]
        raw_entity = raw['entities'][0]
        name = estate.rows['vendors'].get(raw_entity.removeprefix('RFC:'), {}).get('legal_name', raw_entity) if reveal else entity
        parts += [f'<article><h2>{esc(name)} · {esc(", ".join(f["entities"]))} · {esc(f["scheme_type"])}</h2>',
                  f'<p><b>Rule broken:</b> {esc(f["rule_broken"])}</p>',
                  f'<p><b>Amount and confidence:</b> MXN {f["peso_amount"]:,.2f} · {esc(f["confidence"])} · evidence basis: {esc(f.get("basis", "documentary"))}</p>',
                  f'<h3>What happened</h3><p>{esc(f["narrative"])}</p><h3>Money trail</h3>{diagram(f, amount_by_exhibit, parallel)}',
                  '<h3>Exhibits</h3><table><tr><th>Exhibit</th><th>Source table</th><th>Record ID</th><th>What it proves</th></tr>']
        sums = defaultdict(int)
        addends = defaultdict(list)
        for ex, raw_ex in zip(f['exhibits'], raw['exhibits']):
            parts.append(f'<tr id="{esc(ex["exhibit_id"], quote=True)}"><td>{esc(ex["exhibit_id"])}</td><td>{esc(ex["source_table"])}</td><td>{esc(ex["record_id"])}</td><td>{esc(ex["note"])}</td></tr>')
            if raw_ex['source_table'] in AMOUNTS:
                value = amt(estate.row(raw_ex['source_table'], raw_ex['record_id'])[AMOUNTS[raw_ex['source_table']]])
                sums[raw_ex['source_table']] += value
                addends[raw_ex['source_table']].append(f'{ex["exhibit_id"]} ({money(value):,.2f})')
        parts += ['</table><h3>Reconciliation</h3>', '<p>' + ' ; '.join(f'{esc(t)}: {esc(" + ".join(addends[t]))} = MXN {money(v):,.2f}' for t, v in sums.items()) +
                  f'. Claimed = MXN {f["peso_amount"]:,.2f}. Tables are checked separately within 2%; an invoice and the transfer that settled it are the same pesos, so they are not added.</p>',
                  '<h3>Adversarial review</h3><p>Before publication a challenger raised each argument below; the finding was published only because every one failed against the records. The validator then re-checked citations, arithmetic and the trail.</p>',
                  '<table><tr><th>Challenger argument</th><th>Record check</th><th>Outcome</th></tr>']
        for item in f.get('challenges', []):
            parts.append(f'<tr><td>{esc(item["argument"])}</td><td>{esc(item["check"])}</td><td class="held">Accusation held</td></tr>')
        parts.append('</table></article>')
    parts.append('<h2>Leads not pursued</h2><p>Every lead below was investigated with the listed tools and closed without an accusation. "Closed by" names who stopped it: the investigator (not enough corroboration), the challenger (a benign explanation held) or the validator (citations or arithmetic failed).</p>')
    for lead in case['leads_not_pursued']:
        entity_name = estate.rows['vendors'].get(lead['entity'].removeprefix('RFC:'), {}).get('legal_name', lead['entity']) if reveal else lead['entity']
        parts.append(f'<article id="{esc(lead["lead_id"], quote=True)}"><h3>{esc(lead["lead_id"])} · {esc(entity_name)} · {esc(lead["entity"])}</h3>'
                     f'<p><b>Signal:</b> {esc(lead["signal"])} · <b>Closed by:</b> {esc(lead["closed_by"])}</p><p><b>Why closed:</b> {esc(lead["reason"])}</p>'
                     f'<p><small>Tools called: {esc(", ".join(lead["tool_calls_made"]))} · Evidence examined: {esc(", ".join(lead["evidence_examined"]))}</small></p></article>')
    parts += ['<h2>Method and limits</h2>',
              '<p><b>Architecture.</b> A deterministic local controller loads the estate, runs detectors that open leads (SAT 69-B list, supplier master data, invoice-to-payment matching, dated bank-path tracing, approval tiers, CFDI status and payment method, collections), '
              'tests each lead against corroborating records, lets a challenger argue benign explanations, and publishes only findings that pass an independent validator of citations, per-table peso reconciliation and trail continuity. '
              'Optional AI mode lets a model schedule these review steps over pseudonymous aliases; it cannot create or alter findings. No uploaded text is executed.</p>',
              '<p><b>Out of scope for this run:</b></p><ul>' + ''.join(f'<li>{esc(item)}</li>' for item in OUT_OF_SCOPE) + '</ul>',
              '<p><b>What this system cannot detect:</b></p><ul>' + ''.join(f'<li>{esc(item)}</li>' for item in CANNOT_DETECT) + '</ul>',
              '<p><b>Limits:</b></p><ul>' + ''.join(f'<li>{esc(item)}</li>' for item in [*LIMITATIONS, *case.get('warnings', [])]) + '</ul>',
              f'<p><b>Reproducibility.</b> Estate SHA-256: {esc(original["estate_sha256"])} · Rule version: {VERSION}. '
              f'Run <code>python -m forensic_auditor.official run ESTATE --seed {case["seed"]} --company-rfc COMPANY --fresh</code> on the same estate.db or estate_csv.zip; the decision fingerprint must match. '
              'To reproduce this exact file with no network or model calls, run <code>python -m forensic_auditor.official replay RUN.replay.zip --output replay</code>. Original telemetry is retained in replay.</p>',
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
        return {'answer': '\n'.join(f'{l["lead_id"]} ({l["signal"]}, closed by {l["closed_by"]}): {l["reason"]}' for l in matching),
                'evidence': [e for l in matching for e in l['evidence_examined']]}
    matching_f = [f for f in case['findings'] if any(entity.casefold() in lowered for entity in f['entities']) or f['lead_id'].casefold() in lowered]
    if not matching_f and any(word in lowered for word in ('confidence', 'finding', 'evidence', 'amount', 'confianza', 'monto')):
        matching_f = case['findings']
    if matching_f:
        return {'answer': '\n'.join(f'{f["lead_id"]}: {f["confidence"]}; MXN {f["peso_amount"]:.2f}. {f["narrative"]} '
                                    f'Challenges survived: {len(f.get("challenges", []))}.' for f in matching_f),
                'evidence': [f'{e["source_table"]}:{e["record_id"]}' for f in matching_f for e in f['exhibits']]}
    if any(word in lowered for word in ('total', 'cost', 'time')):
        return {'answer': f'Deduplicated exposure MXN {money(exposure(case)):.2f}. Run metadata: {canonical(case["run_metadata"])}', 'evidence': []}
    return {'answer': 'The saved case does not establish that answer. Ask about a listed entity, lead ID, findings, confidence or totals. No investigation was rerun.', 'evidence': []}
