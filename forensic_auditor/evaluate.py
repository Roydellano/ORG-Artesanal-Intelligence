"""Declared synthetic holdout evaluation; never called by the investigator."""
import argparse
import json
from pathlib import Path
import time

from .data import load_zip
from .demo import generate
from .investigation import Investigation


def evaluate(seeds):
    true_positive = false_positive = false_negative = false_accusations = 0
    exact_amounts = valid_citations = findings_count = abstentions = 0
    runtimes = []
    for seed in seeds:
        for clean in (False, True):
            content, truth = generate(seed, clean)
            data = load_zip(content)
            start = time.monotonic()
            job = Investigation(data)
            job.run()
            case = job.snapshot()
            runtimes.append(time.monotonic() - start)
            expected = set(truth["finding_invoice_ids"])
            actual = {row["invoice_id"] for row in case["findings"]}
            true_positive += len(expected & actual)
            false_positive += len(actual - expected)
            false_negative += len(expected - actual)
            false_accusations += len({row["supplier_id"] for row in case["findings"] if row["invoice_id"] not in expected})
            exact_amounts += case["totals"].get("MXN", 0) == truth["expected_excess_centavos"]
            findings_count += len(case["findings"])
            valid_citations += sum(all(ref in data.evidence for ref in finding["evidence"]) for finding in case["findings"])
            abstentions += sum(lead["state"] == "inconclusive" for lead in case["leads"])
    return {"scope": "Fictional excess-settlement and clean-control fixtures only; offline controller. Not production fraud accuracy.",
            "seeds": seeds, "datasets": len(runtimes), "true_positives": true_positive,
            "false_positives": false_positive, "false_negatives": false_negative,
            "precision": true_positive / (true_positive + false_positive) if true_positive + false_positive else None,
            "recall": true_positive / (true_positive + false_negative) if true_positive + false_negative else None,
            "false_supplier_accusations": false_accusations, "exact_amount_datasets": exact_amounts,
            "findings_with_valid_citations": valid_citations, "findings": findings_count,
            "inconclusive_leads": abstentions, "max_runtime_seconds": round(max(runtimes), 4),
            "mean_runtime_seconds": round(sum(runtimes) / len(runtimes), 4)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("tmp/evaluation.json"))
    args = parser.parse_args()
    # Frozen before running this evaluator, distinct from unit and UI seeds.
    result = evaluate([601001, 602003, 603007, 604009, 605021, 606023, 607033, 608041, 609043, 610051])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
