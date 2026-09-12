"""Declared synthetic holdout evaluation; never called by the investigator."""
import argparse
import json
from pathlib import Path
import time
import statistics

from .data import load_zip
from .demo import generate
from .investigation import Investigation


def evaluate_extended(mode="offline"):
    """Exercise the public upload/export API; truth is held only by this evaluator."""
    from fastapi.testclient import TestClient
    from .api import app
    from .scenarios import generate_scenario
    manifest = json.loads((Path(__file__).resolve().parents[1] / "tests/holdout_manifest.json").read_text())
    client = TestClient(app)
    records, runtimes, by_scheme = [], [], {}
    for seed in manifest["seeds"]:
        for scenario in manifest["scenarios"]:
            for benign in manifest["benign"]:
                content, truth = generate_scenario(seed, scenario, benign)
                started = time.monotonic()
                response = client.post("/api/datasets/upload", files={"file": ("records.zip", content, "application/zip")})
                response.raise_for_status()
                base = "/api/datasets/" + response.json()["session_id"]
                start = client.post(base + "/investigate", json={"mode": mode})
                case = {"status": "start_failed", "findings": [], "totals_by_category": {}, "leads": [], "model_calls": 0}
                if start.is_success:
                    while time.monotonic() - started < 125:
                        case = client.get(base + "/case", params={"full": True}).json()
                        if case["status"] not in ("queued", "running"):
                            break
                        time.sleep(.01 if mode == "offline" else .2)
                    export = client.get(base + "/export/json", params={"full": True}).json()
                    valid_refs = set(export["source_evidence"])
                else:
                    valid_refs = set()
                expected = {(f["rule"], f["subject_id"]) for f in truth["findings"]}
                actual = {(f["rule"], f.get("subject_id", f["invoice_id"])) for f in case["findings"]}
                tp, fp, fn = len(expected & actual), len(actual - expected), len(expected - actual)
                metrics = by_scheme.setdefault(scenario, {"true_positive": 0, "false_positive": 0, "false_negative": 0, "datasets": 0})
                for key, value in (("true_positive", tp), ("false_positive", fp), ("false_negative", fn), ("datasets", 1)):
                    metrics[key] += value
                lead_subjects = {l["subject_id"] for l in case["leads"]}
                runtime = time.monotonic() - started
                runtimes.append(runtime)
                records.append({"seed": seed, "scenario": scenario, "benign": benign, "status": case["status"],
                                "exact_categories": case["totals_by_category"] == truth["expected_categories"],
                                "lead_hits": sum(subject in lead_subjects for _, subject in expected), "expected_findings": len(expected),
                                "false_accusations": fp, "valid_citations": all(all(ref in valid_refs for ref in f["evidence"]) for f in case["findings"]),
                                "inconclusive": sum(l["state"] == "inconclusive" for l in case["leads"]),
                                "model_calls": case["model_calls"], "runtime_seconds": round(runtime, 4),
                                "discovery_truncated": case.get("discovery", {}).get("truncated", False)})
                client.delete(base)
    for values in by_scheme.values():
        tp, fp, fn = (values[k] for k in ("true_positive", "false_positive", "false_negative"))
        values["precision"] = tp / (tp + fp) if tp + fp else None
        values["recall"] = tp / (tp + fn) if tp + fn else None
    return {"manifest": manifest, "mode": mode, "datasets": len(records), "by_scheme": by_scheme,
            "completed": sum(r["status"] in ("offline_complete", "complete") for r in records),
            "exact_amount_datasets": sum(r["exact_categories"] for r in records),
            "false_accusations": sum(r["false_accusations"] for r in records),
            "all_citations_valid": all(r["valid_citations"] for r in records),
            "p50_seconds": round(statistics.median(runtimes), 4),
            "p95_seconds": round(sorted(runtimes)[int(.95 * (len(runtimes)-1))], 4),
            "max_seconds": round(max(runtimes), 4), "cost": "Not measured; offline makes no model calls. Live mode requires provider billing data.",
            "records": records}


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
    parser.add_argument("--extended", action="store_true")
    parser.add_argument("--mode", choices=["offline", "ai"], default="offline", help="AI sends only privacy-filtered context; requires eligible configured routing")
    args = parser.parse_args()
    # Frozen before running this evaluator, distinct from unit and UI seeds.
    result = evaluate_extended(args.mode) if args.extended else evaluate([601001, 602003, 603007, 604009, 605021, 606023, 607033, 608041, 609043, 610051])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "records"}, indent=2))
