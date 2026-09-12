"""Versioned, narrow accounting predicates and independent bounded bank discovery."""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import timedelta
import hashlib
import json
import time
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .data import Dataset, load_files
from .engine import LIMITATIONS, generate_leads, reconcile, test_alternative

RULES = {"service": "service-terms-v2", "return": "prohibited-return-v2", "sale": "recognition-terms-v2"}


class Lead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    kind: Literal["invoice", "service", "flow", "return", "sale"]
    subject_id: str
    supplier_id: str = ""
    state: Literal["pending", "investigating", "substantiated", "inconclusive", "dismissed", "deferred"] = "pending"
    hypothesis: str
    reason: str = "Awaiting investigation."
    evidence: list[str]


def lead(kind, subject, refs, hypothesis, supplier=""):
    identity = hashlib.sha256(f"{kind}:{subject}".encode()).hexdigest()[:20]
    return Lead(id=f"{kind}-{identity}", kind=kind, subject_id=subject, supplier_id=supplier,
                hypothesis=hypothesis, evidence=refs).model_dump()


def adjacency(data):
    result = defaultdict(list)
    for tx in data.tables["bank"].values():
        result[tx.source_account].append(tx)
    for rows in result.values():
        rows.sort(key=lambda r: (r.timestamp, r.id))
    return result


def bank_trace(data, root_id, *, graph=None, deadline=None, cancelled=None, budget=1000):
    root = data.tables["bank"][root_id]
    graph = graph if graph is not None else adjacency(data)
    edges = {root.id: root}
    queue = deque([(root.destination_account, root.timestamp, [root.id], {root.source_account, root.destination_account})])
    cycles, examined, truncated = [], 0, False
    while queue:
        if examined >= budget or len(edges) >= 100 or (deadline and time.monotonic() >= deadline) or (cancelled and cancelled.is_set()):
            truncated = True
            break
        account, last, path, visited = queue.popleft()
        if len(path) >= 4:
            continue
        for tx in graph.get(account, []):
            if examined >= budget or len(edges) >= 100 or (deadline and time.monotonic() >= deadline) or (cancelled and cancelled.is_set()):
                truncated = True
                break
            examined += 1
            if tx.currency != root.currency or not last < tx.timestamp <= root.timestamp + timedelta(days=30):
                continue
            edges[tx.id] = tx
            if tx.destination_account == root.source_account:
                cycles.append(path + [tx.id])
            elif tx.destination_account not in visited:
                queue.append((tx.destination_account, tx.timestamp, path + [tx.id], visited | {tx.destination_account}))
    return {"edges": [r.model_dump(mode="json") for r in edges.values()], "cycles": cycles[:20],
            "evidence": [f"bank:{i}" for i in edges], "truncated": truncated,
            "limits": {"depth": 4, "days": 30, "examined_edges": examined, "edges": 100},
            "conclusion": "Observed paths only. These do not establish that the same pesos travelled through each account."}


def discover(data, deadline, cancelled, max_candidates=128, edge_budget=10000):
    leads, seen, examined = [], set(), 0
    truncated = False
    # The existing invoice rule remains compatible; check cancellation between invoices.
    for item in generate_leads(data, deadline=deadline, cancelled=cancelled, max_candidates=max_candidates):
        leads.append(Lead(**item, kind="invoice", subject_id=item["id"]).model_dump())
        if len(leads) >= max_candidates:
            truncated = True
            break
    def add(kind, subject, refs, hypothesis, supplier=""):
        nonlocal truncated
        if len(leads) >= max_candidates or time.monotonic() >= deadline or cancelled.is_set():
            truncated = True
            return
        if (kind, subject) not in seen:
            seen.add((kind, subject))
            leads.append(lead(kind, subject, refs, hypothesis, supplier))
    for contract in data.tables["contracts"].values():
        add("service", contract.invoice_id, [f"contracts:{contract.id}"], "Check payment against documented delivery terms.",
            data.tables["invoices"][contract.invoice_id].supplier_id)
    for sale in data.tables["sales"].values():
        add("sale", sale.id, [f"sales:{sale.id}"], "Check recorded revenue against documented recognition conditions.")
    policy_roots = {r.root_transaction_id for r in data.tables["return_policies"].values()}
    for root in sorted(policy_roots):
        add("return", root, [f"bank:{root}"], "Check a documented prohibited-benefit hypothesis and observed bank legs.")
    graph = adjacency(data)
    allocated = {r.transaction_id for r in data.tables["allocations"].values()}
    refunds = {r.transaction_id for r in data.tables["allocations"].values() if r.kind == "refund"}
    covered_edges = set()
    for root in sorted(data.tables["bank"].values(), key=lambda t: (t.timestamp, t.id)):
        if time.monotonic() >= deadline or cancelled.is_set() or examined >= edge_budget or len(leads) >= max_candidates:
            truncated = True
            break
        if root.id in covered_edges or root.id in policy_roots or root.id in refunds:
            continue
        result = bank_trace(data, root.id, graph=graph, deadline=deadline, cancelled=cancelled,
                            budget=min(1000, edge_budget - examined))
        examined += result["limits"]["examined_edges"]
        truncated |= result["truncated"]
        ids = {row["id"] for row in result["edges"]}
        # A fully allocated payment/refund round trip is already reconciled by the invoice rule.
        meaningful_cycle = any(not set(path) <= allocated for path in result["cycles"])
        if meaningful_cycle or root.id not in allocated:
            add("flow", root.id, result["evidence"], "Investigate a time-ordered cycle or unallocated pass-through; no intent inferred.")
            covered_edges.update(ids)
    truncated |= time.monotonic() >= deadline or cancelled.is_set()
    return leads, {"truncated": truncated, "examined_edges": examined, "candidate_count": len(leads),
                   "candidate_limit": max_candidates, "edge_budget": edge_budget,
                   "coverage": "Implemented predicates only; absence of findings does not establish absence of fraud."}


def ownership(data, account_id, when, refs):
    account = data.tables["accounts"].get(account_id)
    if not account:
        return False
    refs.add(f"accounts:{account_id}")
    rows = [r for r in data.tables["ownership"].values() if r.account_id == account_id and r.valid_from <= when <= r.valid_to]
    refs.update(f"ownership:{r.id}" for r in rows)
    return bool(rows) and all(r.entity_id == account.entity_id for r in rows)


def nondelivery(data, kind, subject, start, end, when, excluded, refs, excluded_sources=()):
    rows = [r for r in data.tables["attestations"].values()
            if r.subject_kind == kind and r.subject_id == subject and r.period_start == start and r.period_end == end]
    refs.update(f"attestations:{r.id}" for r in rows)
    # Conflicting observations are never resolved by voting.
    if any(r.status == "delivered" for r in rows):
        return False, "Contradictory delivery evidence requires human resolution."
    negatives = [r for r in rows if r.status == "not_delivered" and r.as_of >= when and r.issuer_id not in excluded and r.source_id not in excluded_sources]
    if len({r.issuer_id for r in negatives}) < 2 or len({r.source_id for r in negatives}) < 2:
        return False, "Two independently attributed non-delivery records covering the relevant period/date are required."
    return True, "Distinct attributed records corroborate non-delivery; their authenticity is not independently certified."


def assess(data: Dataset, item: dict) -> dict:
    kind, subject = item["kind"], item["subject_id"]
    refs = set()
    missing, checks = [], []
    amount, currency, entity, name = 0, "MXN", "", ""
    calculation = "No supported amount."
    dismissal = False
    extra = {}
    if kind == "flow":
        result = bank_trace(data, subject)
        flow_refs = set(result["evidence"])
        edges = [data.tables["bank"][r["id"]] for r in result["edges"]]
        accounts = [data.tables["accounts"].get(a) for t in edges for a in (t.source_account, t.destination_account)]
        internal = bool(accounts) and all(a and a.kind == "company" for a in accounts) and len({a.entity_id for a in accounts if a}) == 1
        if internal:
            internal = all(ownership(data, a, t.timestamp.date(), flow_refs) for t in edges for a in (t.source_account, t.destination_account))
        result.update(supported=False, dismissed=internal and not result["truncated"],
                      missing=[] if internal and not result["truncated"] else ["Observed paths do not establish a prohibited payment, beneficiary relationship, or transaction linkage."],
                      checks=["All observed legs are between dated accounts of the same company; no external beneficiary is shown." if internal else "No loss is computed from graph cycles."],
                      evidence=sorted(flow_refs), amount_centavos=0, rule="flow-review-v2")
        return result
    if kind == "service":
        invoice = data.tables["invoices"][subject]
        result = reconcile(data, subject)
        refs.update(result["evidence"])
        missing.extend(result["missing"])
        currency, entity = invoice.currency, invoice.supplier_id
        name = data.tables["suppliers"][entity].name
        contracts = [r for r in data.tables["contracts"].values() if r.invoice_id == subject]
        refs.update(f"contracts:{r.id}" for r in contracts)
        if len(contracts) != 1:
            missing.append("Exactly one unambiguous contract is required.")
        else:
            c = contracts[0]
            payments = [data.tables["bank"][a.transaction_id] for a in data.tables["allocations"].values() if a.invoice_id == subject and a.kind == "payment"]
            if c.payment_condition != "delivery":
                dismissal = True
                checks.append("Advance or milestone terms do not establish this delivery-conditioned violation.")
            elif payments:
                when = max(p.timestamp.date() for p in payments)
                if c.due_date < c.period_end or any(p.timestamp.date() < c.due_date for p in payments):
                    missing.append("Payment timing may represent an advance or incomplete contractual period.")
                good, reason = nondelivery(data, "invoice", subject, c.period_start, c.period_end, when,
                                           {invoice.company_id, entity}, refs, {c.source_id})
                checks.append(reason)
                if not good:
                    missing.append(reason)
                receipts = [r for r in data.tables["support"].values() if r.invoice_id == subject]
                refs.update(f"support:{r.id}" for r in receipts)
                if any(r.status == "delivered" for r in receipts):
                    missing.append("An existing receiving record asserts delivery; timing and contradiction require resolution.")
                if any(not ownership(data, account, p.timestamp.date(), refs) for p in payments for account in (p.source_account, p.destination_account)):
                    missing.append("Dated payment account ownership is incomplete or contradictory.")
        amount = max(0, result["net_paid_centavos"])
        calculation = f"max(0, {result['payments_centavos']} - {result['refunds_centavos']}) = {amount} centavos paid contrary to delivery terms"
        checks.extend(test_alternative(data, subject)["checks"])
        if amount == 0:
            dismissal = True
        extra = {"payment_allocations": result["payment_allocations"], "payments_centavos": result["payments_centavos"], "refunds_centavos": result["refunds_centavos"]}
    elif kind == "sale":
        sale = data.tables["sales"][subject]
        customer = data.tables["customers"][sale.customer_id]
        currency, entity, name = sale.currency, sale.customer_id, customer.name
        refs.update([f"sales:{subject}", f"customers:{entity}"])
        ledger = [r for r in data.tables["sale_ledger"].values() if r.sale_id == subject]
        refs.update(f"sale_ledger:{r.id}" for r in ledger)
        amount = sum(r.credit - r.debit for r in ledger)
        if not ledger or any(r.currency != currency for r in ledger) or amount != sale.total - sale.credit:
            missing.append("Revenue subledger does not corroborate net recorded sale after credits.")
        if sale.status == "cancelled":
            missing.append("Cancelled sale requires cancellation/reversal reconciliation outside this rule.")
        if sale.recognition_condition != "delivery":
            dismissal = True
        else:
            when = max([sale.date, *[r.date for r in ledger]])
            good, reason = nondelivery(data, "sale", subject, sale.period_start, sale.period_end, when,
                                      {sale.company_id, sale.customer_id}, refs, {sale.source_id, *[r.source_id for r in ledger]})
            checks.append(reason)
            if not good:
                missing.append(reason)
        checks += ["Unpaid/credit sales alone do not establish false revenue.", "Applied credit/reversal amounts and checked recognition conditions and period."]
        calculation = f"sum(revenue credits - debits) = {amount} centavos; overstatement, not cash loss"
    elif kind == "return":
        root = data.tables["bank"][subject]
        refs.add(f"bank:{subject}")
        currency = root.currency
        policies = [r for r in data.tables["return_policies"].values() if r.root_transaction_id == subject]
        links = [r for r in data.tables["return_links"].values() if r.root_transaction_id == subject]
        refs.update(f"return_policies:{r.id}" for r in policies)
        refs.update(f"return_links:{r.id}" for r in links)
        paths = {tuple(json.loads(r.path)) for r in links}
        if len(paths) != 1 or len({r.source_id for r in links}) < 2 or len({r.issuer_id for r in links}) < 2:
            missing.append("A single observed path requires two distinct attributed linkage records.")
        else:
            path = [data.tables["bank"][i] for i in next(iter(paths))]
            last = path[-1]
            refs.update(f"bank:{t.id}" for t in path)
            if any(a.destination_account != b.source_account or not a.timestamp < b.timestamp for a, b in zip(path, path[1:])) or any(t.currency != currency for t in path) or last.timestamp > root.timestamp + timedelta(days=30):
                missing.append("Bank legs are disconnected, out of order, beyond 30 days, or in different currencies.")
            if any(not ownership(data, a, t.timestamp.date(), refs) for t in path for a in (t.source_account, t.destination_account)):
                missing.append("Dated ownership for every observed bank endpoint is required.")
            recipient = data.tables["accounts"].get(last.destination_account)
            sender = data.tables["accounts"].get(root.source_account)
            if not recipient or not sender or sender.kind != "company":
                missing.append("Company origin and recipient ownership are unresolved.")
            else:
                entity, name = recipient.entity_id, recipient.entity_id
                applicable = [r for r in policies if r.recipient_entity_id == entity and r.valid_from <= root.timestamp.date() and last.timestamp.date() <= r.valid_to]
                if len(applicable) != 1:
                    missing.append("Exactly one applicable prohibition with recipient relationship is required.")
                elif applicable[0].disposition != "prohibited" or applicable[0].purpose != "benefit":
                    if applicable[0].disposition == "permitted":
                        dismissal = True
                    else:
                        missing.append("The supplied policy does not establish a prohibited benefit.")
                if entity == sender.entity_id or recipient.kind == "company":
                    missing.append("A company/internal return may be a legitimate treasury movement.")
                if any(r.source_id in {p.source_id for p in applicable} or r.issuer_id in {entity, sender.entity_id} for r in links):
                    missing.append("Linkage corroboration is not independent of the parties/policy source.")
            if any(a.transaction_id == last.id for a in data.tables["allocations"].values()):
                missing.append("The return is allocated to an invoice and may be a refund or legitimate settlement.")
            amount = last.amount
            extra = {"observed_outflow_centavos": root.amount, "returned_centavos": last.amount,
                     "return_transaction_id": last.id, "edges": [t.model_dump(mode="json") for t in path]}
            calculation = f"observed recipient transfer = {amount} centavos; original outflow {root.amount} reported separately, never summed"
        checks += ["Checked dated prohibition and recipient relationship, ordered bank legs, and independent linkage assertions.",
                   "Refunds, loans, reimbursements, distributions and internal transfers are not treated as prohibited benefits.",
                   "No assumption that identical pesos traversed commingled accounts."]
    supported = amount > 0 and not missing and not dismissal
    return {"supported": supported, "dismissed": dismissal and not missing, "missing": sorted(set(missing)),
            "rule": RULES[kind],
            "checks": checks, "evidence": sorted(refs), "amount_centavos": max(0, amount), "currency": currency,
            "supplier_id": entity, "supplier_name": name, "calculation": calculation, **extra}


def conclude_scheme(data, item):
    verified = load_files(data.files)
    if verified.identity != data.identity:
        raise ValueError("Dataset changed")
    result = assess(verified, item)
    if any(data.evidence.get(ref) != verified.evidence.get(ref) or ref not in verified.evidence for ref in result["evidence"]):
        raise ValueError("Missing or changed evidence")
    if not result["supported"]:
        return None, "dismissed" if result.get("dismissed") else "inconclusive", "; ".join(result["missing"] or result["checks"])
    kind = item["kind"]
    title, category = {"service": ("Payment contrary to documented delivery terms", "service_payment_exposure"),
                       "return": ("Prohibited benefit under supplied payment policy", "observed_prohibited_return"),
                       "sale": ("Revenue contrary to documented recognition terms", "revenue_overstatement")}[kind]
    finding = {"id": f"F-{item['id']}", "rule": RULES[kind], "lead_id": item["id"],
               "subject_id": item["subject_id"], "invoice_id": item["subject_id"],
               "supplier_id": result["supplier_id"], "supplier_name": result["supplier_name"],
               "title": title, "claim": title + ". Established only within the supplied records; intent and authenticity remain unproven.",
               "amount_centavos": result["amount_centavos"], "currency": result["currency"], "amount_type": category,
               "calculation": result, "evidence": result["evidence"], "alternatives": result["checks"], "limitations": LIMITATIONS}
    return finding, "substantiated", title


def totals(findings):
    """Do not add overlapping rule exposures or incompatible amount categories."""
    categories = {}
    for row in findings:
        category, currency = row["amount_type"], row["currency"]
        group = categories.setdefault(category, {}).setdefault(currency, {})
        key = (row["calculation"].get("return_transaction_id") if category == "observed_prohibited_return" else row["invoice_id"])
        group[key] = max(group.get(key, 0), row["amount_centavos"])
    return {category: {currency: sum(items.values()) for currency, items in values.items()} for category, values in categories.items()}


def validate_scheme_finding(data, candidate):
    """Rebuild a serialized finding without trusting its text, numbers or citations."""
    kind = next((kind for kind, rule in RULES.items() if rule == candidate.get("rule")), None)
    if kind is None:
        raise ValueError("Unknown scheme rule")
    item = lead(kind, candidate["subject_id"], [], "Revalidate supplied finding.")
    finding, _, _ = conclude_scheme(data, item)
    if finding is None or finding != candidate:
        raise ValueError("Finding differs from source-validated result")
    return finding
