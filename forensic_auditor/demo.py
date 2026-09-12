"""Fictional seeded records. Evaluator truth is returned separately, never in the ZIP."""
import argparse
import csv
import io
import json
from pathlib import Path
import random
import zipfile

from .data import SCHEMAS


def amount(value: int) -> str:
    return f"{value // 100}.{value % 100:02d}"


def generate(seed: int = 2026, clean: bool = False) -> tuple[bytes, dict]:
    rng = random.Random(seed)
    rows = {table: [] for table in SCHEMAS}
    tag = f"{rng.randrange(10000, 99999)}"
    company = f"ORG-{tag}"
    main = f"AC-{tag}"
    rows["accounts"].append(dict(id=main, entity_id=company, kind="company", source="Fictional bank ownership register"))
    truth = {"seed": seed, "expected_excess_centavos": 0, "finding_invoice_ids": []}
    names = ["Taller Niebla", "Estudio Jacaranda", "Logística Cobre", "Servicios Marea", "Papel Monte", "Consultoría Bruma"]
    for index, name in enumerate(names):
        sid, aid, iid = f"S-{tag}-{index}", f"A-{tag}-{index}", f"I-{tag}-{index}"
        rfc = f"FIC{tag}{index:04d}"
        total = rng.randrange(800_000, 6_000_000)
        day = rng.randrange(2, 15)
        rows["suppliers"].append(dict(id=sid, rfc=rfc, name=f"{name} (ficticio)"))
        rows["accounts"].append(dict(id=aid, entity_id=sid, kind="supplier", source="Fictional bank ownership register"))
        credit = total // 5 if index == 4 else 0
        rows["invoices"].append(dict(id=iid, supplier_id=sid, company_id=company, date=f"2026-08-{day:02d}",
                                    currency="MXN", total=amount(total), credit=amount(credit), status="active",
                                    description="Servicios mensuales según orden de compra"))
        rows["ledger"].append(dict(id=f"L-{tag}-{index}", invoice_id=iid, date=f"2026-08-{day:02d}",
                                  account="Accounts payable obligation", currency="MXN", debit=amount(total), credit=amount(credit)))
        rows["support"].append(dict(id=f"D-{tag}-{index}", invoice_id=iid,
                                   status="not_delivered" if index == 3 and not clean else "delivered",
                                   source="Fictional receiving register", notes="Recorded receiving assertion; review contract and sign-off."))

        def transaction(suffix, value, source=main, destination=aid, kind="payment", hour=10):
            tid = f"T-{tag}-{index}-{suffix}"
            rows["bank"].append(dict(id=tid, timestamp=f"2026-08-{day+1:02d}T{hour:02d}:00:00-06:00",
                                     source_account=source, destination_account=destination, currency="MXN", amount=amount(value), reference=iid))
            rows["allocations"].append(dict(id=f"P-{tag}-{index}-{suffix}", transaction_id=tid,
                                            invoice_id=iid, amount=amount(value), kind=kind))

        if index == 2:  # legitimate split settlement
            transaction("a", total // 2)
            transaction("b", total - total // 2, hour=11)
        else:
            transaction("a", total - credit)
        if index in (0, 1) and not clean:
            excess = rng.randrange(100_000, total)
            transaction("b", excess, hour=11)
            if index == 1:
                transaction("r", excess, source=aid, destination=main, kind="refund", hour=12)
            else:
                truth["expected_excess_centavos"] += excess
                truth["finding_invoice_ids"].append(iid)
        if index == 3 and not clean:
            transit = f"X-{tag}"
            rows["accounts"].append(dict(id=transit, entity_id=f"E-{tag}", kind="other", source="Fictional external statement"))
            for suffix, src, dst, hour in [("x", aid, transit, 11), ("y", transit, main, 12)]:
                rows["bank"].append(dict(id=f"T-{tag}-{index}-{suffix}", timestamp=f"2026-08-{day+1:02d}T{hour}:00:00-06:00",
                                         source_account=src, destination_account=dst, currency="MXN", amount=amount(total // 3), reference="Transfer"))
        if index == 5 and not clean:
            for n, status in enumerate(["presunto", "desvirtuado"]):
                rows["sat"].append(dict(id=f"SAT-{tag}-{n}", rfc=rfc, status=status, publication_date=f"2026-0{6+n}-01",
                                        snapshot_date="2026-08-31", source_url="https://example.invalid/fictional-sat-snapshot"))
    files = {}
    for table, records in rows.items():
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=list(SCHEMAS[table].model_fields))
        writer.writeheader()
        writer.writerows(records)
        files[f"{table}.csv"] = stream.getvalue().encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for filename, content in files.items():
            archive.writestr(filename, content)
    return output.getvalue(), truth


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("demo.zip"))
    parser.add_argument("--truth", type=Path, help="Optional evaluator-only JSON; keep outside uploaded ZIP")
    args = parser.parse_args()
    content, truth = generate(args.seed, args.clean)
    args.output.write_bytes(content)
    if args.truth:
        args.truth.write_text(json.dumps(truth, indent=2), encoding="utf-8")
    print(f"Wrote {args.output}")
