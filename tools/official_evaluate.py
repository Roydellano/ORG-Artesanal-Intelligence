"""Official-format held-out metrics. Never imported by the runtime.

Reports on REPORTING_SEEDS only; detector constants were developed on TUNING_SEEDS. The two sets are disjoint
and asserted so. Records-style estates are the headline (judge-like: prose contracts, company RFC inferred);
typed-style estates exercise the documentary predicates.
"""
import argparse
import csv
import json
from pathlib import Path
import runpy
import time

from .official_generate import generate, generate_records, export_csv_zip, COMPANY, TYPES
from forensic_auditor.official.estate import load, load_zip, infer_company, cents
from forensic_auditor.official.audit import investigate
from forensic_auditor.official.report import canonical, fingerprint

TUNING_SEEDS = [101, 202, 303, 404, 505]
# The first reporting set and a 20-seed sweep exposed two threshold_splitting defects (a Director never seen
# signing above the limit was treated as junior; unrelated small orders split a cluster). After fixing them those
# seeds count as development data. Their first-run results are kept in docs/verification.md.
RETIRED_SEEDS = [710003, 720007, 730013, 740017, 750019, *range(900001, 900021)]
REPORTING_SEEDS = [812007, 823009, 834011, 845013, 856017]  # frozen before any run
assert not set(TUNING_SEEDS + RETIRED_SEEDS) & set(REPORTING_SEEDS)
COLUMNS = 'seed schemes_planted schemes_found recall_pct decoys_planted decoys_accused false_accusation_rate_pct peso_claimed peso_actual peso_reconciles llm_calls mxn_cost wall_clock_s'.split()


def scenario(index):
    """All five (entangled) at the ends, rotating subsets of 2-4 schemes in between."""
    if index in (0, 4):
        return list(TYPES)
    rotated = TYPES[index:] + TYPES[:index]
    return rotated[:index + 1]


def score(case, truth):
    matched, unmatched, amounts_ok = [], [], True
    remaining = list(truth['schemes'])
    for f in case['findings']:
        hit = next((s for s in remaining if s['type'] == f['scheme_type'] and set(s['entities']) & set(f['entities'])), None)
        if hit:
            remaining.remove(hit)
            matched.append((f, hit))
            amounts_ok &= abs(cents(f['peso_amount']) - cents(hit['peso_amount'])) * 100 <= 2 * cents(hit['peso_amount'])
        else:
            unmatched.append(f)
    accused = {e for f in case['findings'] for e in f['entities']}
    decoys_accused = sum(d['entity'] in accused for d in truth['decoys'])
    return matched, unmatched, remaining, decoys_accused, amounts_ok


def evaluate(output, styles=('records', 'typed'), seeds=REPORTING_SEEDS):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    validator = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'specs/student-materials/forensic-auditor/validate_format.py'))
    report = {'tuning_seeds': TUNING_SEEDS, 'retired_seeds_now_development': RETIRED_SEEDS, 'reporting_seeds': list(seeds), 'mode': 'offline', 'styles': {},
              'scope': 'Fictional estates from this project\'s generator only. Not production accuracy or live AI performance.'}
    for style in styles:
        records, details = [], []
        for index, seed in enumerate(seeds):
            path = output / f'{style}-estate-{seed}.db'
            maker = generate_records if style == 'records' else generate
            truth = maker(seed, path, scheme_types=scenario(index))
            (output / f'{style}-answer-key-{seed}.json').write_text(canonical(truth), encoding='utf-8')
            estate = load(path.read_bytes())
            company = infer_company(estate) if style == 'records' else COMPANY
            started = time.perf_counter()
            case = investigate(estate, seed, company)
            elapsed = time.perf_counter() - started
            again = investigate(load(path.read_bytes()), seed, company)
            errors = validator['validate_structure'](case) + validator['validate_against_estate'](case, str(path))
            checks = {'company_inferred_correctly': company == truth['company_rfc'],
                      'deterministic_rerun': fingerprint(case) == fingerprint(again)}
            if index == 0:
                zip_path = output / f'{style}-estate-{seed}.zip'
                export_csv_zip(path, zip_path)
                from_zip = investigate(load_zip(zip_path.read_bytes()), seed, company)
                errors += validator['validate_against_estate_zip'](from_zip, str(zip_path))
                checks['csv_zip_same_decisions'] = fingerprint(from_zip) == fingerprint(case)
            (output / f'{style}-submission-{seed}.json').write_text(canonical(case), encoding='utf-8')
            matched, unmatched, missed, decoys_accused, amounts_ok = score(case, truth)
            claimed = sum(cents(f['peso_amount']) for f in case['findings'])
            actual = sum(cents(s['peso_amount']) for s in truth['schemes'])
            records.append(dict(zip(COLUMNS, [seed, len(truth['schemes']), len(matched),
                                              round(100 * len(matched) / len(truth['schemes']), 1) if truth['schemes'] else 0,
                                              len(truth['decoys']), decoys_accused, round(100 * decoys_accused / len(truth['decoys']), 1),
                                              claimed / 100, actual / 100, not errors and amounts_ok and not unmatched,
                                              case['run_metadata']['llm_calls'], case['run_metadata']['mxn_cost'], round(elapsed, 4)])))
            details.append({'seed': seed, 'status': case['status'], 'format_errors': errors, **checks,
                            'findings': len(case['findings']), 'unmatched_findings': [(f['scheme_type'], f['entities']) for f in unmatched],
                            'missed_schemes': [(s['type'], s['entities'], s['difficulty']) for s in missed],
                            'confidence': {c: sum(f['confidence'] == c for f in case['findings']) for c in ('proven', 'probable')},
                            'leads_not_pursued': len(case['leads_not_pursued']),
                            'closed_by': {c: sum(l['closed_by'] == c for l in case['leads_not_pursued']) for c in ('investigator', 'challenger', 'validator')}})
        totals = {key: sum(r[key] for r in records) for key in ('schemes_planted', 'schemes_found', 'decoys_planted', 'decoys_accused', 'llm_calls', 'mxn_cost')}
        totals.update(seed='TOTAL', recall_pct=round(100 * totals['schemes_found'] / totals['schemes_planted'], 1),
                      false_accusation_rate_pct=round(100 * totals['decoys_accused'] / totals['decoys_planted'], 1),
                      peso_reconciles=all(r['peso_reconciles'] for r in records),
                      peso_claimed=sum(cents(r['peso_claimed']) for r in records) / 100,
                      peso_actual=sum(cents(r['peso_actual']) for r in records) / 100,
                      wall_clock_s=round(sum(r['wall_clock_s'] for r in records), 4))
        name = 'results.csv' if style == 'records' else f'results-{style}.csv'
        with (output / name).open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows([*records, totals])
        report['styles'][style] = {'results_csv': name, 'rows': records, 'totals': totals, 'details': details}
    (output / 'manifest.json').write_text(canonical(report), encoding='utf-8')
    (output / 'results.md').write_text(markdown(report), encoding='utf-8')
    return report


def markdown(report):
    lines = ['# Held-out results', '',
             f"Tuning seeds (development only): {', '.join(map(str, report['tuning_seeds']))}. "
             f"Reporting seeds (never tuned on): {', '.join(map(str, report['reporting_seeds']))}.", '',
             'Retired to development after exposing two defects: 710003, 720007, 730013, 740017, 750019 and sweep seeds 900001-900020 '
             '(first-run results recorded in docs/verification.md).', '',
             f"Scope: {report['scope']}", '']
    for style, data in report['styles'].items():
        title = {'records': 'Records-only estates (judge-like; prose contracts, company RFC inferred)',
                 'typed': 'Typed-contract estates (documentary predicates)'}[style]
        lines += [f'## {title}', '', '| ' + ' | '.join(COLUMNS) + ' |', '|' + '---|' * len(COLUMNS)]
        for row in [*data['rows'], data['totals']]:
            lines.append('| ' + ' | '.join(str(row[c]) for c in COLUMNS) + ' |')
        lines += ['', '| seed | proven/probable | leads closed (investigator/challenger/validator) | deterministic | company inferred | CSV ZIP same | missed | unmatched |', '|---|---|---|---|---|---|---|---|']
        for d in data['details']:
            lines.append(f"| {d['seed']} | {d['confidence']['proven']}/{d['confidence']['probable']} | "
                         f"{d['closed_by']['investigator']}/{d['closed_by']['challenger']}/{d['closed_by']['validator']} | {d['deterministic_rerun']} | "
                         f"{d['company_inferred_correctly']} | {d.get('csv_zip_same_decisions', '—')} | {len(d['missed_schemes'])} | {len(d['unmatched_findings'])} |")
        lines.append('')
    lines += ['Three numbers (offline mode): 0 LLM calls, MXN 0.00 inference cost, wall-clock seconds per estate as listed in wall_clock_s '
              '(investigation only; excludes file load and HTML rendering).', '']
    return '\n'.join(lines)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('tmp/official-evaluation'))
    parser.add_argument('--tuning', action='store_true', help='Run on tuning and retired seeds (development). Never report these numbers.')
    args = parser.parse_args()
    result = evaluate(args.output, seeds=TUNING_SEEDS + RETIRED_SEEDS if args.tuning else REPORTING_SEEDS)
    print(canonical({style: data['totals'] for style, data in result['styles'].items()}))
    print(f'Wrote {args.output / "results.md"}')
