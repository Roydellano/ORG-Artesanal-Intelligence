"""Read-only investigative tools and an independent deterministic evidence gate."""
from __future__ import annotations

from datetime import timedelta
import time
import networkx as nx

from .data import Dataset, pesos

RULE = "excess-settlement-v1"
LIMITATIONS = [
    "Findings establish accounting discrepancies in the supplied records, not fraud or intent.",
    "Excess settlement is recoverable exposure, not demonstrated loss or tax liability.",
    "Records are source-linked but their authenticity and completeness are not independently verified.",
    "External bank movements, beneficial ownership and service delivery may be outside the supplied evidence.",
    "SAT entries are attributed snapshot statuses, never independent proof of fraud.",
]


def related(data: Dataset, table: str, invoice_id: str) -> list:
    return [row for row in data.tables[table].values() if row.invoice_id == invoice_id]


def lookup_supplier(data: Dataset, invoice_id: str) -> dict:
    invoice = data.tables["invoices"][invoice_id]
    supplier = data.tables["suppliers"][invoice.supplier_id]
    accounts = [row for row in data.tables["accounts"].values() if row.entity_id == supplier.id]
    sat = sorted([row for row in data.tables["sat"].values() if row.rfc == supplier.rfc],
                 key=lambda row: (row.snapshot_date, row.publication_date))
    return {"supplier": supplier.model_dump(), "accounts": [row.model_dump() for row in accounts],
            "sat_history": [row.model_dump(mode="json") for row in sat],
            "interpretation": "Status history only; no inference about invoice fraud.",
            "evidence": [f"suppliers:{supplier.id}"] + [f"accounts:{row.id}" for row in accounts]
                        + [f"sat:{row.id}" for row in sat]}


def reconcile(data: Dataset, invoice_id: str) -> dict:
    invoice = data.tables["invoices"][invoice_id]
    allocations = related(data, "allocations", invoice_id)
    ledger = related(data, "ledger", invoice_id)
    refs = {f"invoices:{invoice_id}", f"suppliers:{invoice.supplier_id}"}
    missing = []
    paid = returned = 0
    used = []
    for item in allocations:
        tx = data.tables["bank"][item.transaction_id]
        source = data.tables["accounts"].get(tx.source_account)
        destination = data.tables["accounts"].get(tx.destination_account)
        refs.update([f"allocations:{item.id}", f"bank:{tx.id}"])
        if source:
            refs.add(f"accounts:{source.id}")
        if destination:
            refs.add(f"accounts:{destination.id}")
        company, supplier = (source, destination) if item.kind == "payment" else (destination, source)
        valid = (company and supplier and company.kind == "company" and supplier.kind == "supplier"
                 and company.entity_id == invoice.company_id and supplier.entity_id == invoice.supplier_id
                 and tx.currency == invoice.currency)
        if not valid:
            missing.append(f"Allocation {item.id} lacks matching company/supplier account ownership.")
        if item.kind == "payment":
            paid += item.amount
            used.append({"transaction_id": tx.id, "allocation_id": item.id, "centavos": item.amount})
        else:
            returned += item.amount
    # An unexplained transfer to/from this supplier may be a refund, advance or consolidated settlement.
    allocation_totals = {}
    for row in data.tables["allocations"].values():
        allocation_totals[row.transaction_id] = allocation_totals.get(row.transaction_id, 0) + row.amount
    supplier_accounts = {row.id for row in data.tables["accounts"].values() if row.entity_id == invoice.supplier_id}
    for tx in data.tables["bank"].values():
        if tx.currency != invoice.currency:
            continue
        endpoints = {tx.source_account, tx.destination_account}
        unknown = any(account not in data.tables["accounts"] for account in endpoints)
        if (endpoints & supplier_accounts or unknown) and tx.amount != allocation_totals.get(tx.id, 0):
            refs.add(f"bank:{tx.id}")
            missing.append(f"Unallocated bank amount on {tx.id}; refund/settlement attribution is unresolved.")
    obligation = 0 if invoice.status == "cancelled" else invoice.total - invoice.credit
    refs.update(f"ledger:{row.id}" for row in ledger)
    if not ledger or any(row.currency != invoice.currency for row in ledger):
        missing.append("Missing or currency-inconsistent invoice ledger corroboration.")
    elif sum(row.debit - row.credit for row in ledger) != obligation:
        missing.append("Ledger net does not corroborate the invoice obligation after credits/cancellation.")
    if returned > paid:
        missing.append("Allocated refunds exceed payments; settlement history is incomplete.")
    excess = max(0, paid - returned - obligation)
    return {"invoice_id": invoice_id, "supplier_id": invoice.supplier_id, "currency": invoice.currency,
            "invoiced_centavos": invoice.total, "credits_centavos": invoice.credit,
            "obligation_centavos": obligation, "payments_centavos": paid, "refunds_centavos": returned,
            "net_paid_centavos": paid - returned, "excess_centavos": excess,
            "calculation": f"max(0, {paid} - {returned} - {obligation}) = {excess} centavos",
            "missing": sorted(set(missing)), "evidence": sorted(refs), "payment_allocations": used,
            "rule": RULE}


def check_support(data: Dataset, invoice_id: str) -> dict:
    rows = related(data, "support", invoice_id)
    return {"records": [row.model_dump() for row in rows], "evidence": [f"support:{row.id}" for row in rows],
            "conclusion": ("Conflicting delivery assertions; authenticity, timing and contract terms need review."
                           if any(row.status == "not_delivered" for row in rows)
                           else "No verified service-delivery violation established.")}


def test_alternative(data: Dataset, invoice_id: str) -> dict:
    result = reconcile(data, invoice_id)
    return {"evidence": result["evidence"], "checks": [
        f"Included allocated refunds: {pesos(result['refunds_centavos'], result['currency'])}.",
        "Used explicit payment allocations; split/consolidated payments count only their allocated amounts.",
        "Applied invoice credit/cancellation and checked ledger net and both account owners.",
        "Unallocated supplier transfers or unknown owners prevent publication.",
    ], "unresolved": result["missing"]}


def trace_funds(data: Dataset, invoice_id: str, *, depth: int = 4, max_edges: int = 100) -> dict:
    """Strictly time-increasing, same-currency paths, capped by depth, edges and 30 days."""
    invoice = data.tables["invoices"][invoice_id]
    graph = nx.MultiDiGraph()
    for tx in data.tables["bank"].values():
        if tx.currency == invoice.currency:
            graph.add_edge(tx.source_account, tx.destination_account, key=tx.id, tx=tx)
    roots = [data.tables["bank"][row.transaction_id] for row in related(data, "allocations", invoice_id)
             if row.kind == "payment"]
    edges = {}
    cycles = []
    examined = 0
    truncated = False
    for root in roots:
        if len(edges) >= max_edges:
            truncated = True
            break
        edges[root.id] = root
        queue = [(root.destination_account, root.timestamp, [root.id], {root.source_account, root.destination_account})]
        while queue and examined < 1000 and len(edges) < max_edges:
            account, last_time, path, visited = queue.pop(0)
            if len(path) >= depth:
                continue
            outgoing = sorted(graph.out_edges(account, keys=True, data=True), key=lambda edge: edge[3]["tx"].timestamp)
            for _, destination, tx_id, attrs in outgoing:
                examined += 1
                if examined > 1000 or len(edges) >= max_edges:
                    truncated = True
                    break
                tx = attrs["tx"]
                if not last_time < tx.timestamp <= root.timestamp + timedelta(days=30):
                    continue
                edges[tx_id] = tx
                if destination == root.source_account:
                    cycles.append(path + [tx_id])
                elif destination not in visited:
                    queue.append((destination, tx.timestamp, path + [tx_id], visited | {destination}))
    return {"edges": [row.model_dump(mode="json") for row in edges.values()], "cycles": cycles[:20],
            "evidence": [f"bank:{key}" for key in edges], "truncated": truncated or examined >= 1000,
            "conclusion": "Paths show observed transfers, not attribution of the same pesos or proof of kickbacks.",
            "limits": {"depth": depth, "days": 30, "edges": max_edges, "examined_edges": examined}}


def generate_leads(data: Dataset, *, deadline=None, cancelled=None, max_candidates=128) -> list[dict]:
    leads = []
    priority = {}
    for invoice in data.tables["invoices"].values():
        if (deadline and time.monotonic() >= deadline) or (cancelled and cancelled.is_set()):
            break
        result = reconcile(data, invoice.id)
        supplier = lookup_supplier(data, invoice.id)
        support = check_support(data, invoice.id)
        reasons = []
        if result["payments_centavos"] > result["obligation_centavos"]:
            reasons.append("Gross payments exceed the recorded obligation; test refunds and allocations.")
        if result["missing"]:
            reasons.append("Settlement evidence has unresolved gaps.")
        if any(row["status"] == "not_delivered" for row in support["records"]):
            reasons.append("Supporting records dispute delivery.")
        if supplier["sat_history"]:
            reasons.append("Review dated SAT history without inferring fraud.")
        if reasons:
            priority[invoice.id] = result["excess_centavos"]
            leads.append({"id": invoice.id, "supplier_id": invoice.supplier_id, "state": "pending",
                          "hypothesis": " ".join(reasons), "reason": "Awaiting investigation.",
                          "evidence": [f"invoices:{invoice.id}"]})
            if len(leads) >= max_candidates:
                break
    return sorted(leads, key=lambda lead: (-priority[lead["id"]], lead["id"]))


def validate_finding(data: Dataset, candidate: dict) -> dict:
    """Recompute from source bytes; caller-supplied conclusions cannot bypass the gate."""
    from .data import load_files
    verified = load_files(data.files)
    if verified.identity != data.identity:
        raise ValueError("Dataset changed")
    result = reconcile(verified, candidate["invoice_id"])
    if result["missing"] or result["excess_centavos"] <= 0:
        raise ValueError("Required evidence or excess-settlement predicate is missing")
    if candidate.get("rule") != RULE or candidate.get("amount_centavos") != result["excess_centavos"]:
        raise ValueError("Rule or arithmetic mismatch")
    if set(candidate.get("evidence", [])) != set(result["evidence"]):
        raise ValueError("Required evidence set differs")
    for ref in result["evidence"]:
        if data.evidence.get(ref) != verified.evidence[ref]:
            raise ValueError("Evidence is missing or changed")
    supplier = verified.tables["suppliers"][result["supplier_id"]]
    return {"id": f"F-{result['invoice_id']}", "rule": RULE, "invoice_id": result["invoice_id"],
            "supplier_id": supplier.id, "supplier_name": supplier.name,
            "title": "Excess settlement against recorded obligation",
            "claim": f"Allocated net payments exceed the corroborated obligation for invoice {result['invoice_id']}.",
            "amount_centavos": result["excess_centavos"], "currency": result["currency"],
            "amount_type": "excess_settlement_exposure", "calculation": result,
            "evidence": result["evidence"], "alternatives": test_alternative(verified, result["invoice_id"])["checks"],
            "limitations": LIMITATIONS[:3]}


def conclude(data: Dataset, invoice_id: str) -> tuple[dict | None, str, str]:
    result = reconcile(data, invoice_id)
    if result["missing"]:
        return None, "inconclusive", " ".join(result["missing"])
    if result["excess_centavos"] > 0:
        finding = validate_finding(data, {"invoice_id": invoice_id, "rule": RULE,
                                         "amount_centavos": result["excess_centavos"], "evidence": result["evidence"]})
        return finding, "substantiated", "Verified excess-settlement discrepancy; intent remains unproven."
    support = check_support(data, invoice_id)
    if any(row["status"] == "not_delivered" for row in support["records"]):
        return None, "inconclusive", "Delivery is disputed; contract terms and independent corroboration are missing."
    if lookup_supplier(data, invoice_id)["sat_history"]:
        return None, "inconclusive", "SAT history alone does not establish an invoice violation or loss."
    return None, "dismissed", "Credits, refunds and explicit allocations explain the gross-payment lead."
