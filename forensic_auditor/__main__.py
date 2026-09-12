"""Offline CLI backup using the same ingestion and controller as the web app."""
import argparse
import json
from pathlib import Path

from .data import load_zip, persist
from .investigation import Investigation
from .reporting import export_case, printable

parser = argparse.ArgumentParser()
parser.add_argument("dataset", type=Path)
parser.add_argument("--mode", choices=["offline", "ai"], default="offline")
parser.add_argument("--output", type=Path, default=Path("case-file"))
parser.add_argument("--sqlite", type=str, help="Optional local provenance archive")
args = parser.parse_args()
data = load_zip(args.dataset.read_bytes())
job = Investigation(data, args.mode)
job.run()
case = job.snapshot()
args.output.with_suffix(".json").write_text(json.dumps(export_case(data, case), indent=2, ensure_ascii=False), encoding="utf-8")
args.output.with_suffix(".html").write_text(printable(data, case), encoding="utf-8")
if args.sqlite:
    persist(data, args.sqlite)
print(json.dumps({"status": case["status"], "findings": len(case["findings"]), "totals_centavos": case["totals"]}))
