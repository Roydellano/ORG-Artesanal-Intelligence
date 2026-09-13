"""Runtime-path official estate CLI and network-free completed-run replay."""
import argparse
from pathlib import Path
import sys

from .estate import load_any, infer_company
from .audit import investigate
from .report import canonical, fingerprint, render, bundle, replay


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest='command', required=True)
    run = commands.add_parser('run')
    run.add_argument('estate', type=Path, help='estate.db (SQLite) or estate_csv.zip')
    run.add_argument('--seed', type=int, required=True)
    run.add_argument('--company-rfc', help='Audited company RFC; inferred from invoices when omitted')
    run.add_argument('--output', type=Path, default=Path('tmp/official-case'))
    run.add_argument('--fresh', action='store_true', help='Measure a new run instead of replaying a matching completed output')
    run.add_argument('--mode', choices=['offline', 'ai'], default='offline')
    run.add_argument('--usd-mxn-rate')
    run.add_argument('--fx-source', default='')
    run.add_argument('--zdr', dest='zdr', action='store_true', default=None, help='Enforce Zero Data Retention (ZDR) routing')
    run.add_argument('--no-zdr', dest='zdr', action='store_false', help='Disable ZDR routing for testing with free models or providers without ZDR')
    rerun = commands.add_parser('replay')
    rerun.add_argument('archive', type=Path)
    rerun.add_argument('--output', type=Path, default=Path('tmp/replayed-case'))
    args = parser.parse_args()
    if args.command == 'replay':
        estate, case = replay(args.archive.read_bytes())
    else:
        estate = load_any(args.estate.read_bytes())
        company = args.company_rfc or infer_company(estate)
        if not args.company_rfc:
            print(f'Audited company RFC inferred from invoices: {company}', file=sys.stderr)
        existing = args.output.with_suffix('.replay.zip')
        case = None
        if existing.exists() and not args.fresh:
            old_estate, old_case = replay(existing.read_bytes())
            if old_estate.identity == estate.identity and old_case['seed'] == args.seed and old_case['company_rfc'] == company and old_case['run_metadata']['mode'] == args.mode:
                case = old_case
        if case is None:
            if args.mode == 'ai':
                from .agent import run as ai_run
                case = ai_run(estate, args.seed, company, usd_mxn_rate=args.usd_mxn_rate, fx_source=args.fx_source, zdr=args.zdr)
            else:
                case = investigate(estate, args.seed, company)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    archive = bundle(estate, case)
    args.output.with_suffix('.json').write_text(canonical(case), encoding='utf-8')
    args.output.with_suffix('.html').write_text(render(estate, case, reveal=True), encoding='utf-8')
    args.output.with_suffix('.masked.html').write_text(render(estate, case), encoding='utf-8')
    args.output.with_suffix('.replay.zip').write_bytes(archive)
    print(canonical({'status': case['status'], 'company_rfc': case['company_rfc'], 'findings': len(case['findings']),
                     'leads_not_pursued': len(case['leads_not_pursued']), 'decision_fingerprint': fingerprint(case),
                     'run_metadata': case['run_metadata']}))


if __name__ == '__main__':
    main()
