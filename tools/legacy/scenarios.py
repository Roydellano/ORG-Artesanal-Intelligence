"""Fictional independent injections. Truth is returned separately from uploaded CSVs."""
import csv
from datetime import timedelta
import io
import json
import random
import zipfile

from forensic_auditor.data import SCHEMAS, load_zip
from tools.legacy.demo import generate, amount

SCENARIOS = ("all", "excess", "service", "return", "sale", "cycle")


def pack(rows):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for table, records in rows.items():
            stream = io.StringIO(newline="")
            writer = csv.DictWriter(stream, fieldnames=list(SCHEMAS[table].model_fields))
            writer.writeheader()
            writer.writerows(records)
            archive.writestr(f"{table}.csv", stream.getvalue().encode())
    return output.getvalue()


def inject_scenario(content, seed, scenario, benign=False):
    if scenario not in SCENARIOS:
        raise ValueError("Unknown scenario")
    data = load_zip(content)
    if not data.tables["invoices"] or any("(ficticio)" not in s.name for s in data.tables["suppliers"].values()):
        raise ValueError("Scheme injection requires explicitly fictional suppliers.")
    rng = random.Random(seed)
    tag = f"{rng.getrandbits(56):014x}"
    rows = {table: list(csv.DictReader(io.StringIO(data.files[f"{table}.csv"].decode()))) if f"{table}.csv" in data.files else [] for table in SCHEMAS}
    invoices = sorted(data.tables["invoices"].values(), key=lambda r: r.id)
    chosen = ["excess", "service", "return", "sale", "cycle"] if scenario == "all" else [scenario]
    truth = {"rules": {}, "expected_categories": {}, "findings": [], "seed": seed, "benign": benign}
    def add(table, **values):
        record = dict(version="2", **values) if "version" in SCHEMAS[table].model_fields else values
        rows[table].append(record)
    def expected(rule, category, value, subject):
        if not benign:
            truth["rules"][rule] = truth["rules"].get(rule, 0) + 1
            truth["expected_categories"][category] = {"MXN": value}
            truth["findings"].append({"rule": rule, "subject_id": subject, "amount_centavos": value})
    for index, kind in enumerate(chosen):
        invoice = invoices[index % len(invoices)]
        allocations = [r for r in data.tables["allocations"].values() if r.invoice_id == invoice.id and r.kind == "payment"]
        if not allocations:
            raise ValueError("Injection requires a settled fictional invoice")
        original = data.tables["bank"][allocations[0].transaction_id]
        company, supplier = original.source_account, original.destination_account
        when = original.timestamp.date()
        if kind == "excess":
            value = rng.randrange(10000, 90000)
            tid = "T-" + tag
            add("bank", id=tid, timestamp=(original.timestamp + timedelta(hours=1)).isoformat(), source_account=company, destination_account=supplier,
                currency="MXN", amount=amount(value), reference=invoice.id)
            add("allocations", id="P-" + tag, transaction_id=tid, invoice_id=invoice.id, amount=amount(value), kind="payment")
            if benign:
                add("bank", id=tid + "R", timestamp=(original.timestamp + timedelta(hours=2)).isoformat(), source_account=supplier, destination_account=company,
                    currency="MXN", amount=amount(value), reference=invoice.id)
                add("allocations", id="P-" + tag + "R", transaction_id=tid + "R", invoice_id=invoice.id, amount=amount(value), kind="refund")
            expected("excess-settlement-v1", "excess_settlement_exposure", value, invoice.id)
        elif kind == "service":
            start, end = invoice.date.isoformat(), invoice.date.isoformat()
            add("contracts", id="C-" + tag, invoice_id=invoice.id, period_start=start, period_end=end, due_date=when.isoformat(),
                payment_condition="advance" if benign else "delivery", source_id="Contract-" + tag)
            # Remove old fictional generic receipt for this subject; the new dated records define this scenario.
            rows["support"] = [r for r in rows["support"] if r["invoice_id"] != invoice.id]
            for n in range(2):
                add("attestations", id=f"A-{tag}-{n}", subject_kind="invoice", subject_id=invoice.id,
                    period_start=start, period_end=end, as_of=when.isoformat(), status="not_delivered",
                    issuer_id=f"Reviewer-{tag}-{n}", source_id=f"Report-{tag}-{n}")
            net = sum(a.amount if a.kind == "payment" else -a.amount for a in data.tables["allocations"].values() if a.invoice_id == invoice.id)
            expected("service-terms-v2", "service_payment_exposure", net, invoice.id)
        elif kind == "return":
            bridge, recipient = "B-" + tag, "K-" + tag
            beneficiary = "E-" + tag
            add("accounts", id=bridge, entity_id="Transit-" + tag, kind="other", source="Fictional external statement")
            add("accounts", id=recipient, entity_id=beneficiary, kind="other", source="Fictional beneficiary statement")
            value = rng.randrange(10000, 90000)
            a, b = "X-" + tag, "Y-" + tag
            for tid, src, dst, hours in ((a, supplier, bridge, 2), (b, bridge, recipient, 3)):
                add("bank", id=tid, timestamp=(original.timestamp + timedelta(hours=hours)).isoformat(), source_account=src, destination_account=dst,
                    currency="MXN", amount=amount(value), reference="Fictional transfer")
            add("return_policies", id="Policy-" + tag, root_transaction_id=original.id, recipient_entity_id=beneficiary,
                valid_from="2026-01-01", valid_to="2026-12-31", disposition="permitted" if benign else "prohibited",
                purpose="reimbursement" if benign else "benefit", source_id="Terms-" + tag)
            for n in range(2):
                add("return_links", id=f"Link-{tag}-{n}", root_transaction_id=original.id, return_transaction_id=b,
                    path=json.dumps([original.id, a, b]), issuer_id=f"Investigator-{tag}-{n}", source_id=f"Linkage-{tag}-{n}")
            expected("prohibited-return-v2", "observed_prohibited_return", value, original.id)
        elif kind == "sale":
            customer, sale = "Customer-" + tag, "Sale-" + tag
            value = rng.randrange(10000, 90000)
            add("customers", id=customer, name="Cliente Horizonte (ficticio)", rfc="FIC" + tag)
            add("sales", id=sale, customer_id=customer, company_id=invoice.company_id, date=when.isoformat(),
                period_start=invoice.date.isoformat(), period_end=invoice.date.isoformat(), currency="MXN", total=amount(value), credit="0.00",
                status="active", recognition_condition="unconditional" if benign else "delivery", source_id="SalesTerms-" + tag)
            add("sale_ledger", id="Revenue-" + tag, sale_id=sale, date=when.isoformat(), currency="MXN", debit="0.00", credit=amount(value), source_id="Receivables-" + tag)
            for n in range(2):
                add("attestations", id=f"SA-{tag}-{n}", subject_kind="sale", subject_id=sale, period_start=invoice.date.isoformat(),
                    period_end=invoice.date.isoformat(), as_of=when.isoformat(), status="not_delivered",
                    issuer_id=f"SalesReviewer-{tag}-{n}", source_id=f"SalesReport-{tag}-{n}")
            expected("recognition-terms-v2", "revenue_overstatement", value, sale)
        elif kind == "cycle":
            bridge = "Treasury-" + tag
            add("accounts", id=bridge, entity_id=invoice.company_id, kind="company", source="Fictional treasury ownership")
            for n, src, dst in ((1, company, bridge), (2, bridge, company)):
                add("bank", id=f"Internal-{tag}-{n}", timestamp=(original.timestamp + timedelta(days=n)).isoformat(),
                    source_account=src, destination_account=dst, currency="MXN", amount="500.00", reference="Internal treasury transfer")
    for n, account in enumerate(rows["accounts"]):
        if not any(r["account_id"] == account["id"] for r in rows["ownership"]):
            add("ownership", id=f"Owner-{tag}-{n}", account_id=account["id"], entity_id=account["entity_id"],
                valid_from="2026-01-01", valid_to="2026-12-31", source_id=f"BankOwnership-{tag}-{n}")
    result = pack(rows)
    load_zip(result)  # Validate the public contract, not the expected answer.
    return result, truth


def generate_scenario(seed, scenario="all", benign=False):
    content, _ = generate(seed, clean=True)
    return inject_scenario(content, seed + 7919, scenario, benign)
