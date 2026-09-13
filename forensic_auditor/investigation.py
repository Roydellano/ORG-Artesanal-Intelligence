"""Bounded controller. Model choices never create claims or calculated amounts."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import threading
import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from openrouter_client import chat, OpenRouterError, OpenRouterRateLimit, settings, DEFAULT_MODEL, PRIVACY_VERSION
from .privacy import ModelProjection, POLICY
from .schemes import discover, assess, bank_trace, conclude_scheme, totals as category_totals
from .data import Dataset
from .engine import (LIMITATIONS, check_support, conclude, generate_leads,
                     lookup_supplier, reconcile, test_alternative, trace_funds)

PROMPT_VERSION = "investigator-v3"
MIN_MODEL_SECONDS = 15
TOOLS = {"lookup_supplier": lookup_supplier, "reconcile": reconcile,
         "check_support": check_support, "test_alternative": test_alternative, "trace_funds": trace_funds}
SYSTEM = """You are a forensic investigation controller reviewing pseudonymous structured facts.
Return only JSON: {"lead_id":"exact supplied alias","tool":"one available_tools entry"}.
Prefer {"actions":[...]} with one action per pending lead, up to 12 DISTINCT leads per response.
Prefer inspect_evidence to gather the required local checks together. Then test_alternative, then conclude.
Use only the exact supplied lead aliases and each lead's available_tools. Never repeat completed tools.
Inspect evidence before alternatives, and alternatives before conclude. Prioritize strong leads, then resolve uncertain leads.
The deterministic evidence gate alone decides findings and amounts. Do not include prose or private reasoning.
"""


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lead_id: str = Field(min_length=1, max_length=500)
    tool: Literal["inspect_evidence", "lookup_supplier", "reconcile", "check_support", "trace_funds", "test_alternative", "conclude"]


class Investigation:
    def __init__(self, data: Dataset, mode: str = "offline", max_steps: int = 60, seconds: float = 180, model_chat=chat, *, synthetic=False):
        self.data = data
        self.mode = mode
        self.max_steps = max_steps
        self.seconds = seconds
        self.model_chat = model_chat
        self.synthetic = synthetic
        self.projection = ModelProjection()
        self.cancelled = threading.Event()
        self.lock = threading.RLock()
        self.cache = {}  # Per investigation only; never shared between uploads or users.
        self.seen = set()
        self.completed_tools = {}
        self.results = {}
        self.actions = []
        self.resume_pending = False
        self.resume_count = 0
        self.model = settings()["model"] if mode == "ai" else DEFAULT_MODEL
        self.case = {"dataset_id": data.identity, "version": "case-v2", "mode": mode, "status": "queued",
                     "model": self.model if mode == "ai" else None, "prompt_version": PROMPT_VERSION,
                     "leads": [], "findings": [], "timeline": [], "totals": {}, "limitations": LIMITATIONS,
                     "warnings": data.warnings, "elapsed_seconds": 0, "model_calls": 0,
                     "coverage": {table: len(rows) for table, rows in data.tables.items()},
                     "totals_by_category": {}, "privacy_policy": POLICY,
                     "provider_policy": "fictional-demo-only" if synthetic else PRIVACY_VERSION,
                     "total_definition": "Categories are non-additive: service exposure may overlap excess settlement; observed returns and revenue overstatement are separate from cash loss."}

    def snapshot(self) -> dict:
        with self.lock:
            return deepcopy(self.case)

    def event(self, lead_id: str, tool: str, result: dict) -> None:
        with self.lock:
            self.case["timeline"].append({"step": len(self.case["timeline"]) + 1, "lead_id": lead_id,
                                          "tool": tool, "result": result, "prompt_version": PROMPT_VERSION,
                                          "rule_version": result.get("rule"), "evidence": result.get("evidence", [])})

    @staticmethod
    def sequence(lead):
        if lead["kind"] == "invoice":
            return [*TOOLS, "conclude"]
        if lead["kind"] in ("flow", "return"):
            return ["trace_funds", "check_support", "test_alternative", "conclude"]
        return ["reconcile", "check_support", "test_alternative", "conclude"]

    @classmethod
    def available(cls, lead, used):
        sequence = cls.sequence(lead)
        required = {"reconcile", "test_alternative"} if lead["kind"] == "invoice" else set(sequence[:-1])
        available = [tool for tool in sequence if tool not in used and (tool != "conclude" or required <= used)]
        if any(tool not in used for tool in sequence if tool not in ("test_alternative", "conclude")):
            available.insert(0, "inspect_evidence")
        return available

    def run(self) -> None:
        started = time.monotonic()
        seen = self.seen
        completed_tools = self.completed_tools
        results = self.results
        actions = self.actions
        try:
            with self.lock:
                self.case["status"] = "running"
            if self.resume_pending:
                leads, discovery = self.case["leads"], self.case["discovery"]
                self.resume_pending = False
            else:
                leads, discovery = discover(self.data, started + self.seconds, self.cancelled)
            with self.lock:
                self.case["leads"] = leads
                self.case["discovery"] = discovery
            for step in range(max(0, self.max_steps - len(seen))):
                if len(seen) >= self.max_steps and any(lead["state"] in ("pending", "investigating") for lead in leads):
                    with self.lock:
                        self.case["error_type"] = "step_budget"
                        self.case["can_resume"] = self.resume_count < 5
                    self._finish("incomplete", "Step budget reached.")
                    break
                if self.cancelled.is_set():
                    self._finish("cancelled", "Cancelled by the reviewer.")
                    break
                remaining = self.seconds - (time.monotonic() - started)
                if remaining <= 0:
                    with self.lock:
                        self.case["error_type"] = "timeout"
                        self.case["can_resume"] = self.resume_count < 5
                    self._finish("incomplete", "Investigation time budget reached.")
                    break
                pending = [lead for lead in leads if lead["state"] in ("pending", "investigating")]
                if not pending:
                    self._finish("incomplete" if discovery["truncated"] else ("complete" if self.mode == "ai" else "offline_complete"), "Discovery truncated." if discovery["truncated"] else "All generated leads reviewed; implemented rule coverage only.")
                    break
                if self.mode == "ai":
                    if not actions:
                        if remaining < MIN_MODEL_SECONDS:
                            with self.lock:
                                self.case["error_type"] = "timeout"
                                self.case["can_resume"] = self.resume_count < 5
                            self._finish("incomplete", "Investigation time budget reached. Continue with more time to proceed.")
                            break
                        payload = self.projection.context(pending, completed_tools, results, self.available)
                        if len(payload) > 80_000:
                            raise ValueError("Context budget exceeded")
                        key = hashlib.sha256(f"{self.data.identity}:{self.model}:{PROMPT_VERSION}:{POLICY}:{payload}".encode()).hexdigest()
                        if key not in self.cache:
                            with self.lock:
                                self.case["model_calls"] += 1
                            config = settings()
                            if config["model"] != self.model:
                                raise OpenRouterError("Model configuration changed during this investigation. Start a new case to use the new model.")
                            call_timeout = config["timeout"]
                            kwargs = {"max_tokens": config["max_tokens"], "timeout": min(call_timeout, max(15.0, remaining))}
                            if self.model_chat is chat:
                                kwargs["synthetic"] = self.synthetic
                            self.cache[key] = self.model_chat([{"role": "system", "content": SYSTEM},
                                                               {"role": "user", "content": payload}], **kwargs)
                        response = self.cache[key].strip()
                        # Accept a single fenced JSON document, never extract JSON from arbitrary prose.
                        if response.startswith("```json\n") and response.endswith("\n```"):
                            response = response[8:-4]
                        parsed = json.loads(response)
                        batch = parsed["actions"] if isinstance(parsed, dict) and set(parsed) == {"actions"} else [parsed]
                        if not isinstance(batch, list) or not 1 <= len(batch) <= 12:
                            raise ValueError("Invalid action batch")
                        proposed_actions = [Action.model_validate(value) for value in batch]
                        if len({a.lead_id for a in proposed_actions}) != len(proposed_actions):
                            raise ValueError("Batch must contain distinct leads")
                        for proposed in proposed_actions:
                            proposed.lead_id = self.projection.resolve(proposed.lead_id)
                            target = next((p for p in pending if p["id"] == proposed.lead_id), None)
                            if target is None or proposed.tool not in self.available(target, completed_tools.get(target["id"], set())):
                                raise ValueError("Action is not currently available")
                        actions = proposed_actions
                        self.actions = actions
                    action = actions[0]
                else:
                    lead = pending[0]
                    sequence = self.sequence(lead)
                    action = Action(lead_id=lead["id"], tool=next(tool for tool in sequence if (lead["id"], tool) not in seen))
                if self.cancelled.is_set() or time.monotonic() - started >= self.seconds:
                    with self.lock:
                        if not self.cancelled.is_set():
                            self.case["error_type"] = "timeout"
                            self.case["can_resume"] = self.resume_count < 5
                    self._finish("cancelled" if self.cancelled.is_set() else "incomplete", "Stopped before applying the next action.")
                    break
                if self.mode == "ai":
                    actions.pop(0)
                lead = next((lead for lead in pending if lead["id"] == action.lead_id), None)
                if not lead or (action.lead_id, action.tool) in seen or action.tool not in self.available(lead, completed_tools.get(lead["id"], set())):
                    raise ValueError("Unknown lead or repeated tool call")
                seen.add((action.lead_id, action.tool))
                with self.lock:
                    lead["state"] = "investigating"
                if action.tool == "conclude":
                    if "conclude" not in self.available(lead, completed_tools.get(lead["id"], set())):
                        raise ValueError("Cannot conclude without reconciliation and an alternative check")
                    finding, state, reason = (conclude(self.data, lead["subject_id"]) if lead["kind"] == "invoice" else conclude_scheme(self.data, lead))
                    with self.lock:
                        lead.update(state=state, reason=reason)
                        if finding:
                            self.case["findings"].append(finding)
                            self.case["totals_by_category"] = category_totals(self.case["findings"])
                            self.case["totals"] = self.case["totals_by_category"].get("excess_settlement_exposure", {})
                    self.event(lead["id"], "conclude", {"state": state, "reason": reason,
                                                         "rule": finding["rule"] if finding else None,
                                                         "evidence": finding["evidence"] if finding else lead["evidence"]})
                elif action.tool == "inspect_evidence":
                    seen.discard((lead["id"], "inspect_evidence"))
                    for tool in self.sequence(lead):
                        if tool in ("test_alternative", "conclude") or tool in completed_tools.get(lead["id"], set()):
                            continue
                        if len(seen) >= self.max_steps or self.cancelled.is_set() or time.monotonic() - started >= self.seconds:
                            break
                        if lead["kind"] == "invoice":
                            result = TOOLS[tool](self.data, lead["subject_id"])
                        elif tool == "trace_funds":
                            result = bank_trace(self.data, lead["subject_id"], deadline=started + self.seconds, cancelled=self.cancelled)
                        else:
                            result = assess(self.data, lead)
                        self.data.retrieve(result["evidence"])
                        results[lead["id"]] = result
                        completed_tools.setdefault(lead["id"], set()).add(tool)
                        seen.add((lead["id"], tool))
                        with self.lock:
                            lead["evidence"] = sorted(set(lead["evidence"]) | set(result["evidence"]))
                        self.event(lead["id"], tool, result)
                else:
                    if lead["kind"] == "invoice":
                        result = TOOLS[action.tool](self.data, lead["subject_id"])
                    elif action.tool == "trace_funds":
                        result = bank_trace(self.data, lead["subject_id"], deadline=started + self.seconds, cancelled=self.cancelled)
                    else:
                        result = assess(self.data, lead)
                    results[lead["id"]] = result
                    self.data.retrieve(result["evidence"])
                    completed_tools.setdefault(lead["id"], set()).add(action.tool)
                    with self.lock:
                        lead["evidence"] = sorted(set(lead["evidence"]) | set(result["evidence"]))
                    self.event(lead["id"], action.tool, result)
            else:
                unresolved = any(lead["state"] in ("pending", "investigating") for lead in leads)
                if unresolved:
                    with self.lock:
                        self.case["error_type"] = "step_budget"
                        self.case["can_resume"] = self.resume_count < 5
                self._finish("incomplete" if unresolved or discovery["truncated"] else ("complete" if self.mode == "ai" else "offline_complete"),
                             "Step budget reached." if unresolved else ("Discovery truncated." if discovery["truncated"] else "All generated leads reviewed."))
        except OpenRouterRateLimit as error:
            with self.lock:
                self.case["error_type"] = "rate_limited"
                self.case["retry_at"] = time.time() + error.retry_after if error.retry_after is not None else None
                self.case["can_resume"] = self.resume_count < 5
            self._finish("incomplete", str(error))
        except OpenRouterError as error:
            msg = str(error)
            err_type = "timeout" if "timeout" in msg.lower() else ("connection_error" if any(w in msg.lower() for w in ("connection", "network", "502", "503")) else "provider_error")
            with self.lock:
                self.case["error_type"] = err_type
                self.case["can_resume"] = self.resume_count < 5
            self._finish("incomplete", msg)
        except (ValueError, KeyError, TypeError):
            self._finish("incomplete", "Invalid controller response or evidence validation failure. No unchecked finding was published.")
        except Exception:
            self._finish("incomplete", "Investigation stopped after an internal error. Review server diagnostics and retry.")
        finally:
            with self.lock:
                self.case["elapsed_seconds"] = round(self.case.get("elapsed_seconds", 0) + time.monotonic() - started, 3)

    def prepare_resume(self, mode: str, seconds: float | None = None, max_steps: int | None = None):
        """User-requested recovery only; retain validated findings, aliases and tool results."""
        with self.lock:
            if self.case["status"] != "incomplete" or self.resume_count >= 5:
                raise ValueError("Only incomplete investigations can resume, up to five times per case.")
            if mode == "ai":
                if settings()["model"] != self.model:
                    raise ValueError("The model changed. Start a new investigation to use the new model.")
                retry_at = self.case.get("retry_at")
                if retry_at and time.time() < retry_at:
                    raise ValueError(f"The provider requested a cooldown. Try resuming in {max(1, int(retry_at-time.time())+1)} seconds, or finish offline.")
            elif mode != "offline":
                raise ValueError("Unknown review mode")
            self.resume_count += 1
            self.mode = mode
            self.case["mode"] = mode
            if seconds:
                self.seconds = float(seconds)
            if max_steps:
                self.max_steps = max(self.max_steps, len(self.seen) + max_steps)
            self.case["recovery"] = ("AI review resumed with more time" if mode == "ai" and seconds
                                     else ("AI review resumed" if mode == "ai"
                                           else "User selected offline completion after partial review"))
            self.case["can_resume"] = False
            self.case.pop("error_type", None)
            self.case.pop("retry_at", None)
            self.case["status"] = "queued"
            self.case["completion_reason"] = self.case["recovery"]
            self.cancelled.clear()
            for lead in self.case["leads"]:
                if lead["state"] == "deferred":
                    lead.update(state="investigating" if self.completed_tools.get(lead["id"]) else "pending", reason="Resuming remaining review.")
            if mode == "offline":
                self.actions.clear()
            self.resume_pending = True
            self.event("case", "resume_review", {"mode": mode, "attempt": self.resume_count, "evidence": [], "reason": self.case["recovery"], "seconds": self.seconds})

    def _finish(self, status: str, reason: str):
        with self.lock:
            self.case["status"] = status
            self.case["completion_reason"] = reason
            for lead in self.case["leads"]:
                if lead["state"] in ("pending", "investigating"):
                    lead.update(state="deferred", reason=reason)


def answer(case: dict, question: str) -> dict:
    """Extractive case Q&A: every displayed factual passage comes from validated case fields."""
    text = question.lower()
    findings = case["findings"]
    selected = [f for f in findings if any(str(f.get(key, "")).lower() in text for key in ("id", "invoice_id", "supplier_id", "supplier_name") if f.get(key))]
    if selected:
        findings = selected
    else:
        families = {"service": "service-terms-v2", "delivery": "service-terms-v2", "sale": "recognition-terms-v2", "revenue": "recognition-terms-v2", "return": "prohibited-return-v2", "excess": "excess-settlement-v1"}
        requested = {rule for word, rule in families.items() if word in text}
        if requested:
            findings = [f for f in findings if f["rule"] in requested]
    refs = set()
    if any(word in text for word in ("intent", "guilty", "criminal", "home address", "culpable")):
        sections = ["The current case cannot substantiate intent, guilt, or private personal details. Supplied records establish only the stated accounting predicates."]
    elif any(word in text for word in ("missing", "change", "unknown", "falta", "evidence", "support", "relationship", "evidencia")):
        sections = []
        for finding in findings:
            sections.append(f"{finding['id']}: {finding['claim']}\nChecks: " + "; ".join(finding["alternatives"]) + "\nLimits: " + "; ".join(finding["limitations"]))
            refs.update(finding["evidence"])
        for lead in case["leads"]:
            if lead["state"] in ("inconclusive", "deferred") and (not findings or lead.get("subject_id") in {f["invoice_id"] for f in findings}):
                sections.append(f"{lead['id']}: {lead['reason']}")
                refs.update(lead["evidence"])
        sections.append("Conflicting delivery, permissions, refunds or ownership evidence can change a conclusion; re-upload corrected records for revalidation.")
    elif any(word in text for word in ("amount", "total", "much", "cuánto", "monto", "calcula")):
        sections = [f"Separate amount categories by currency (centavos): {json.dumps(case.get('totals_by_category', {'excess_settlement_exposure': case['totals']}))}. Categories may overlap and must not be summed. This is not demonstrated loss."]
        for finding in findings:
            sections.append(f"{finding['invoice_id']}: {finding['calculation']['calculation']}")
            refs.update(finding["evidence"])
    elif any(word in text for word in ("dismiss", "why", "inconclusive", "lead", "descart", "por qué", "reason")):
        sections = [f"{lead['id']} — {lead['state']}: {lead['reason']}" for lead in case["leads"]]
        refs.update(ref for lead in case["leads"] for ref in lead["evidence"])
    elif any(word in text for word in ("finding", "supplier", "prove", "fraud", "proveedor", "hallazgo")):
        sections = [f"{finding['supplier_name']}: {finding['claim']}" for finding in findings]
        sections.append("These are supported accounting discrepancies; fraud, intent and beneficial ownership are not established.")
        refs.update(ref for finding in findings for ref in finding["evidence"])
    else:
        sections = ["The current case cannot substantiate that answer. Ask about totals, calculations, findings or why a lead was dismissed. For other questions, inspect the source records and obtain additional evidence."]
    return {"answer": "\n\n".join(sections), "evidence": sorted(refs), "mode": "extractive",
            "case_status": case["status"]}
