"""Runtime-path official estate CLI and network-free completed-run replay."""
import argparse
from pathlib import Path

from .estate import load
from .audit import investigate
from .report import canonical, render, bundle, replay


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest='command', required=True)
    run = commands.add_parser('run')
    run.add_argument('estate', type=Path)
    run.add_argument('--seed', type=int, required=True)
    run.add_argument('--company-rfc', required=True)
    run.add_argument('--output', type=Path, default=Path('tmp/official-case'))
    run.add_argument('--fresh', action='store_true', help='Measure a new run instead of replaying a matching completed output')
    run.add_argument('--mode', choices=['offline', 'ai'], default='offline')
    run.add_argument('--usd-mxn-rate')
    run.add_argument('--fx-source', default='')
    rerun = commands.add_parser('replay')
    rerun.add_argument('archive', type=Path)
    rerun.add_argument('--output', type=Path, default=Path('tmp/replayed-case'))
    args = parser.parse_args()
    if args.command == 'replay':
        estate, case = replay(args.archive.read_bytes())
    else:
        estate = load(args.estate.read_bytes())
        existing = args.output.with_suffix('.replay.zip')
        case = None
        if existing.exists() and not args.fresh:
            old_estate, old_case = replay(existing.read_bytes())
            if old_estate.identity == estate.identity and old_case['seed'] == args.seed and old_case['company_rfc'] == args.company_rfc and old_case['run_metadata']['mode'] == args.mode:
                case = old_case
        if case is None:
            if args.mode == 'ai':
                from .agent import run as ai_run
                case = ai_run(estate, args.seed, args.company_rfc, usd_mxn_rate=args.usd_mxn_rate, fx_source=args.fx_source)
            else:
                case = investigate(estate, args.seed, args.company_rfc)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    archive = bundle(estate, case)
    args.output.with_suffix('.json').write_text(canonical(case), encoding='utf-8')
    args.output.with_suffix('.html').write_text(render(estate, case, reveal=True), encoding='utf-8')
    args.output.with_suffix('.masked.html').write_text(render(estate, case), encoding='utf-8')
    args.output.with_suffix('.replay.zip').write_bytes(archive)
    print(canonical({'status': case['status'], 'findings': len(case['findings']), 'run_metadata': case['run_metadata']}))


if __name__ == '__main__':
    main()
