"""Allowlisted external context. Original values never enter this projection."""
from __future__ import annotations

import json
import re
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field

POLICY = "projection-v1"
TOOL_NAMES = {"inspect_evidence", "lookup_supplier", "reconcile", "check_support", "trace_funds", "test_alternative", "conclude"}
KINDS = {"invoice", "service", "flow", "return", "sale"}


class SafeLead(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(pattern=r"^L-[a-f0-9]{32}$")
    kind: str
    completed_tools: list[str]
    available_tools: list[str]
    evidence_count: int = Field(ge=0)
    missing_count: int = Field(ge=0)
    supported: bool
    amounts_centavos: dict[str, int]
    observed_edges: int = Field(ge=0)
    observed_cycles: int = Field(ge=0)


class ModelProjection:
    def __init__(self):
        self.session = uuid4().hex
        self.forward = {}
        self.reverse = {}

    def alias(self, value: str) -> str:
        if value not in self.forward:
            alias = "L-" + uuid4().hex
            while alias in self.reverse:
                alias = "L-" + uuid4().hex
            self.forward[value] = alias
            self.reverse[alias] = value
        return self.forward[value]

    def resolve(self, alias: str) -> str:
        if alias not in self.reverse:
            raise ValueError("Unknown or cross-session lead alias")
        return self.reverse[alias]

    def context(self, leads: list, completed: dict, results: dict, available) -> str:
        rows = []
        for lead in leads:
            used = sorted(completed.get(lead["id"], set()))
            allowed = available(lead, set(used))
            result = results.get(lead["id"], {})
            amount_fields = {"payments_centavos", "refunds_centavos", "obligation_centavos", "excess_centavos", "amount_centavos", "net_paid_centavos", "returned_centavos", "observed_outflow_centavos"}
            amounts = {key: result[key] for key in sorted(amount_fields) if key in result}
            if any(type(value) is not int or abs(value) > 2 * 10**15 for value in amounts.values()):
                raise ValueError("Invalid model-facing amount")
            row = SafeLead(id=self.alias(lead["id"]), kind=lead.get("kind", "invoice"),
                           completed_tools=used, available_tools=allowed,
                           evidence_count=len(result.get("evidence", [])),
                           missing_count=len(result.get("missing", result.get("unresolved", []))),
                           supported=result.get("supported", False) is True, amounts_centavos=amounts,
                           observed_edges=len(result.get("edges", [])), observed_cycles=len(result.get("cycles", [])))
            if row.kind not in KINDS or not set(used + allowed) <= TOOL_NAMES:
                raise ValueError("Unexpected model-facing value")
            rows.append(row.model_dump())
        # Only these fields can cross the boundary, regardless of raw timeline contents.
        return json.dumps({"dataset_id": self.session, "leads": rows,
                           "completed_tools": {r["id"]: r["completed_tools"] for r in rows}}, ensure_ascii=True)

    def clear(self):
        self.forward.clear()
        self.reverse.clear()


class Presentation:
    """Stable per-session aliases for local masked API views and shareable exports."""
    OMIT = {"description", "reference", "notes", "source", "source_url", "question", "path"}
    IDS = {"id", "entity_id", "supplier_id", "company_id", "invoice_id", "transaction_id",
           "source_account", "destination_account", "customer_id", "sale_id", "account_id",
           "root_transaction_id", "return_transaction_id", "recipient_entity_id", "rfc", "name", "account",
           "source_id", "issuer_id", "subject_id", "lead_id", "supplier_name", "allocation_id"}

    def __init__(self, data):
        self.mapping = {}
        self.reverse = {}
        self.used = set()
        for table, records in data.tables.items():
            for record in records.values():
                self.token(f"{table}:{record.id}")
                for key, value in record.model_dump(mode="json").items():
                    if key in self.IDS and isinstance(value, str):
                        self.token(value)
        for record in data.evidence.values():
            for key, raw in record["original"].items():
                if key in self.IDS:
                    normalized = record["normalized"].get(key)
                    self.mapping[raw] = self.token(normalized) if isinstance(normalized, str) else self.token(raw)
        # Longest-first avoids replacing an ID inside a longer reference first.
        self.pattern = re.compile(r"(?<![\w-])(?:" + "|".join(re.escape(v) for v in sorted(self.mapping, key=len, reverse=True)) + r")(?![\w-])") if self.mapping else None

    def token(self, value):
        if value not in self.mapping:
            token = "R-" + uuid4().hex[:12]
            while token in self.used:
                token = "R-" + uuid4().hex[:12]
            self.used.add(token)
            self.mapping[value] = token
            self.reverse[token] = value
        return self.mapping[value]

    def prepare(self, value):
        """Include derived finding/lead IDs before masking prose that mentions them."""
        before = len(self.mapping)
        def visit(item):
            if isinstance(item, dict):
                for key, child in item.items():
                    if key in self.IDS and isinstance(child, str) and child and child != "case":
                        self.token(child)
                    visit(child)
            elif isinstance(item, list):
                for child in item: visit(child)
        visit(value)
        if len(self.mapping) != before:
            self.pattern = re.compile(r"(?<![\w-])(?:" + "|".join(re.escape(v) for v in sorted(self.mapping, key=len, reverse=True)) + r")(?![\w-])")

    def apply(self, value, key=""):
        if key == "":
            self.prepare(value)
        if key in self.OMIT:
            return "[omitted in masked view]"
        if isinstance(value, dict):
            return {(self.mapping.get(k, k) if key == "source_evidence" else k): self.apply(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [self.apply(v, key) for v in value]
        if isinstance(value, str):
            if key in self.IDS:
                if value in ("case", ""):
                    return value
                token = self.token(value)
                return token
            if key in {"calculation", "currency", "date", "timestamp", "period_start", "period_end", "as_of", "valid_from", "valid_to", "due_date", "total", "amount", "debit", "credit", "version", "status", "kind", "payment_condition", "recognition_condition", "disposition", "purpose"}:
                return value
            return self.pattern.sub(lambda m: self.mapping[m.group()], value) if self.pattern else value
        return value
