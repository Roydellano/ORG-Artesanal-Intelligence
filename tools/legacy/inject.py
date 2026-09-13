"""Independent excess-payment injection for explicitly fictional datasets only."""
import argparse
import csv
from datetime import timedelta
import io
import json
from pathlib import Path
import random
import zipfile

from forensic_auditor.data import load_zip
from tools.legacy.demo import amount
from forensic_auditor.engine import reconcile


def inject(content: bytes, seed: int) -> tuple[bytes, dict]:
    data = load_zip(content)
    eligible = []
    for invoice in data.tables["invoices"].values():
        supplier = data.tables["suppliers"][invoice.supplier_id]
        check = reconcile(data, invoice.id)
        if "(ficticio)" in supplier.name and not check["missing"] and check["net_paid_centavos"] == check["obligation_centavos"] and check["payments_centavos"] > 0:
            eligible.append(invoice)
    if not eligible:
        raise ValueError("No fully settled invoice from an explicitly fictional supplier is eligible.")
    rng = random.Random(seed)
    invoice = rng.choice(eligible)
    payment = next(row for row in data.tables["allocations"].values() if row.invoice_id == invoice.id and row.kind == "payment")
    original = data.tables["bank"][payment.transaction_id]
    new_id = f"TX-{rng.getrandbits(64):016x}"
    if new_id in data.tables["bank"] or new_id in data.tables["allocations"]:
        raise ValueError("Injection ID collision; use a different seed")
    value = rng.randrange(10000, 1000000)
    rows_to_add = {
        "bank": dict(id=new_id, timestamp=(original.timestamp + timedelta(days=1)).isoformat(),
                     source_account=original.source_account, destination_account=original.destination_account,
                     currency=original.currency, amount=amount(value), reference=invoice.id),
        "allocations": dict(id=new_id, transaction_id=new_id, invoice_id=invoice.id, amount=amount(value), kind="payment"),
    }
    files = dict(data.files)
    for table, new_row in rows_to_add.items():
        reader = csv.DictReader(io.StringIO(files[f"{table}.csv"].decode("utf-8-sig")))
        fields, rows = reader.fieldnames, list(reader)
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows([*rows, new_row])
        files[f"{table}.csv"] = stream.getvalue().encode()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for filename, body in files.items():
            archive.writestr(filename, body)
    return stream.getvalue(), {"invoice_id": invoice.id, "currency": invoice.currency,
                              "added_excess_centavos": value, "seed": seed}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--truth", type=Path, required=True, help="Evaluator-only file, never upload it")
    parser.add_argument("--scheme", choices=["excess", "service", "return", "sale", "cycle", "all"], default="excess")
    parser.add_argument("--benign", action="store_true")
    args = parser.parse_args()
    if args.scheme == "excess" and not args.benign:
        content, truth = inject(args.dataset.read_bytes(), args.seed)
    else:
        from tools.legacy.scenarios import inject_scenario
        content, truth = inject_scenario(args.dataset.read_bytes(), args.seed, args.scheme, args.benign)
    args.output.write_bytes(content)
    args.truth.write_text(json.dumps(truth, indent=2), encoding="utf-8")
    print(f"Wrote {args.output}; truth saved separately.")
