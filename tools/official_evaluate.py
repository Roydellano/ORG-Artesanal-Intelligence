"""Official-format held-out metrics. Never imported by the runtime."""
import argparse
import csv
import json
from pathlib import Path
import runpy

from .official_generate import generate, COMPANY, TYPES
from forensic_auditor.official.estate import load, cents
from forensic_auditor.official.audit import investigate
from forensic_auditor.official.report import canonical

TUNING_SEEDS = [101, 202, 303]
REPORTING_SEEDS = [710003, 720007, 730013, 740017, 750019]
COLUMNS = 'seed schemes_planted schemes_found recall_pct decoys_planted decoys_accused false_accusation_rate_pct peso_claimed peso_actual peso_reconciles llm_calls mxn_cost wall_clock_s'.split()


def evaluate(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    validator = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'specs/student-materials/forensic-auditor/validate_format.py'))
    records = []
    for index, seed in enumerate(REPORTING_SEEDS):
        path = output / f'estate-{seed}.db'
        # Vary planted counts, retain entanglement in all-five scenarios.
        selected = TYPES if index in (0, 4) else TYPES[:index+1]
        truth = generate(seed, path, scheme_types=selected)
        (output / f'answer-key-{seed}.json').write_text(canonical(truth), encoding='utf-8')
        case = investigate(load(path.read_bytes()), seed, COMPANY)
        errors = validator['validate_structure'](case) + validator['validate_against_estate'](case, str(path))
        (output / f'submission-{seed}.json').write_text(canonical(case), encoding='utf-8')
        actual = {(f['scheme_type'], tuple(sorted(f['entities']))): cents(f['peso_amount']) for f in case['findings']}
        expected = {(s['type'], tuple(sorted(s['entities']))): cents(s['peso_amount']) for s in truth['schemes']}
        found = len(actual.keys() & expected.keys())
        accused = {entity for f in case['findings'] for entity in f['entities']}
        decoys_accused = sum(d['entity'] in accused for d in truth['decoys'])
        records.append(dict(zip(COLUMNS, [seed, len(expected), found, 100*found/len(expected) if expected else 0,
                              len(truth['decoys']), decoys_accused, 100*decoys_accused/len(truth['decoys']),
                              sum(actual.values())/100, sum(expected.values())/100, not errors and actual == expected,
                              case['run_metadata']['llm_calls'], case['run_metadata']['mxn_cost'], case['run_metadata']['wall_clock_seconds']])))
        if errors:
            raise ValueError(errors)
    totals = {key: sum(r[key] for r in records) for key in COLUMNS if key not in ('seed', 'recall_pct', 'false_accusation_rate_pct', 'peso_reconciles')}
    totals.update(seed='TOTAL', recall_pct=100*totals['schemes_found']/totals['schemes_planted'],
                  false_accusation_rate_pct=100*totals['decoys_accused']/totals['decoys_planted'],
                  peso_reconciles=all(r['peso_reconciles'] for r in records))
    for key in ('peso_claimed', 'peso_actual'):
        totals[key] = sum(cents(r[key]) for r in records) / 100
    with (output / 'results.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows([*records, totals])
    metadata = {'tuning_seeds': TUNING_SEEDS, 'reporting_seeds': REPORTING_SEEDS, 'mode': 'offline',
                'scope': 'Fictional supported-contract fixtures only. Not production accuracy or live AI performance.',
                'totals': totals}
    (output / 'manifest.json').write_text(canonical(metadata), encoding='utf-8')
    return metadata


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('tmp/official-evaluation'))
    print(canonical(evaluate(parser.parse_args().output)))
