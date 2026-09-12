"""Generation process emits records only; evaluator answers never enter the API process."""
import argparse
import sys
from forensic_auditor.demo import generate
from forensic_auditor.scenarios import generate_scenario

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--seed', type=int, required=True)
    parser.add_argument('--scenario', choices=['legacy', 'all', 'excess', 'service', 'return', 'sale', 'cycle'], required=True)
    parser.add_argument('--clean', action='store_true')
    args = parser.parse_args()
    records, _ = generate(args.seed, args.clean) if args.scenario == 'legacy' else generate_scenario(args.seed, args.scenario, args.clean)
    sys.stdout.buffer.write(records)
