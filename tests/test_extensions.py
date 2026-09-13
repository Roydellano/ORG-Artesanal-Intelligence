import csv
from copy import deepcopy
import io
import json
import threading
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from forensic_auditor.api import app, sessions
from forensic_auditor.data import load_zip, load_files
from tools.legacy.demo import generate
from forensic_auditor.investigation import Investigation, answer
from forensic_auditor.privacy import ModelProjection, Presentation
from forensic_auditor.reporting import export_case, printable
from tools.legacy.scenarios import generate_scenario, pack
from forensic_auditor.schemes import discover, conclude_scheme, bank_trace, totals
from forensic_auditor.schemes import validate_scheme_finding
from openrouter_client import chat, OpenRouterError


def run(data, **kwargs):
    job = Investigation(data, **kwargs)
    job.run()
    return job.snapshot()


def mutate(data, table, fn):
    rows = {name: list(csv.DictReader(io.StringIO(body.decode()))) for name, body in ((key[:-4], value) for key, value in data.files.items())}
    fn(rows[table])
    return load_zip(pack(rows))


@pytest.mark.parametrize("seed", [12811, 17317, 67129])
@pytest.mark.parametrize("scenario", ["all", "service", "return", "sale", "cycle"])
def test_fresh_schemes_and_benign_controls(seed, scenario):
    for benign in (False, True):
        content, truth = generate_scenario(seed, scenario, benign)
        data = load_zip(content)
        case = run(data)
        assert case["status"] == "offline_complete"
        assert case["totals_by_category"] == truth["expected_categories"]
        assert sorted(f["rule"] for f in case["findings"]) == sorted(truth["rules"])
        assert all(all(ref in data.evidence for ref in f["evidence"]) for f in case["findings"])


@pytest.mark.parametrize("scenario,table", [("service", "attestations"), ("service", "ownership"),
                                           ("service", "ledger"), ("return", "ownership"),
                                           ("return", "return_links"), ("sale", "sale_ledger"), ("sale", "attestations")])
def test_removing_required_records_prevents_publication(scenario, table):
    data = load_zip(generate_scenario(67129, scenario)[0])
    data = mutate(data, table, lambda rows: rows.clear())
    assert not run(data)["findings"]


@pytest.mark.parametrize("scenario", ["service", "sale"])
@pytest.mark.parametrize("change", ["delivered", "same_source", "same_issuer", "wrong_period"])
def test_contradictions_and_copied_assertions_are_not_proof(scenario, change):
    data = load_zip(generate_scenario(98817, scenario)[0])
    def edit(rows):
        if change == "delivered": rows[0]["status"] = "delivered"
        if change == "same_source": rows[1]["source_id"] = rows[0]["source_id"]
        if change == "same_issuer": rows[1]["issuer_id"] = rows[0]["issuer_id"]
        if change == "wrong_period": rows[0].update(period_start="2026-01-01", period_end="2026-01-01")
    assert not run(mutate(data, "attestations", edit))["findings"]


def test_expired_ownership_and_forged_source_evidence_block_return():
    data = load_zip(generate_scenario(6799, "return")[0])
    expired = mutate(data, "ownership", lambda rows: [row.update(valid_to="2026-01-02") for row in rows])
    assert not run(expired)["findings"]
    lead = next(row for row in discover(data, time.monotonic()+10, threading.Event())[0] if row["kind"] == "return")
    data.evidence[next(iter(data.refs("return_links")))] = {"forged": True}
    with pytest.raises(ValueError): conclude_scheme(data, lead)


def test_service_respects_legacy_delivery_contradiction():
    data = load_zip(generate_scenario(6799, "service")[0])
    subject = next(iter(data.tables["contracts"].values())).invoice_id
    data = mutate(data, "support", lambda rows: rows.append(dict(id="contradiction", invoice_id=subject, status="delivered", source="receipt", notes="")))
    assert not run(data)["findings"]


def test_independent_bank_cycle_without_invoice_anomaly_and_budgets():
    data = load_zip(generate_scenario(675, "cycle")[0])
    leads, coverage = discover(data, time.monotonic()+10, threading.Event())
    assert any(row["kind"] == "flow" for row in leads)
    assert not any(row["kind"] == "invoice" for row in leads)
    assert not run(data)["findings"]
    assert any(l["state"] == "dismissed" for l in run(data)["leads"])
    assert discover(data, time.monotonic()-1, threading.Event())[1]["truncated"]
    cancel = threading.Event(); cancel.set()
    assert discover(data, time.monotonic()+10, cancel)[1]["truncated"]
    assert discover(data, time.monotonic()+10, threading.Event(), edge_budget=1)[1]["truncated"]


def scripted(messages, **kwargs):
    context = json.loads(messages[1]["content"])
    return json.dumps({"actions": [{"lead_id": r["id"], "tool": r["available_tools"][0]} for r in context["leads"][:6]]})


def test_model_transport_never_receives_pii_or_raw_questions():
    data = load_zip(generate_scenario(721, "all")[0])
    canary = "sensitive-SSN-987-65-4321-PRIVATE"
    data = mutate(data, "suppliers", lambda rows: [r.update(name=canary, rfc=canary.lower()) for r in rows])
    data = mutate(data, "bank", lambda rows: [r.update(reference=canary) for r in rows])
    job = Investigation(data, mode="ai", model_chat=scripted)
    job.event("case", "answer_question", {"question": canary, "evidence": []})
    requests = []
    def transport(request, **kwargs):
        body = json.loads(request.data)
        requests.append(body)
        result = scripted(body["messages"])
        return io.BytesIO(json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": result}}]}).encode())
    with patch("openrouter_client.dotenv_values", return_value={"OPENROUTER_API_KEY": "key", "OPENROUTER_MODEL": "test/private"}), patch.dict("os.environ", {}, clear=True), patch("openrouter_client.urlopen", side_effect=transport):
        job = Investigation(data, mode="ai")
        job.event("case", "answer_question", {"question": canary, "evidence": []})
        job.run()
    assert job.snapshot()["status"] == "complete"
    for body in requests:
        text = json.dumps(body)
        assert canary not in text and canary.lower() not in text and canary.upper() not in text
        assert all(str(r.id) not in text for r in data.tables["bank"].values())
        assert body["provider"] == {"data_collection": "deny", "zdr": True, "allow_fallbacks": False, "require_parameters": True}
    for output in (json.dumps(export_case(data, job.snapshot())), printable(data, job.snapshot())):
        assert canary not in output and canary.lower() not in output and canary.upper() not in output
    assert canary in json.dumps(export_case(data, job.snapshot(), full=True))


def test_aliases_are_session_scoped_and_unknown_values_fail():
    a, b = ModelProjection(), ModelProjection()
    alias = a.alias("original-id")
    assert a.alias("original-id") == alias
    assert b.alias("original-id") != alias
    with pytest.raises(ValueError): b.resolve(alias)
    a.clear()
    with pytest.raises(ValueError): a.resolve(alias)


def test_presentation_alias_resolves_normalized_id_with_original_whitespace():
    data = load_zip(generate_scenario(339, "excess")[0])
    original_id = next(iter(data.tables["bank"]))
    data = mutate(data, "bank", lambda rows: rows[0].update(id="  " + original_id + "  "))
    presentation = Presentation(data)
    alias = presentation.apply(data.tables["bank"][original_id].model_dump(mode="json"))["id"]
    presentation.apply(data.evidence[f"bank:{original_id}"])
    assert presentation.reverse[alias] == original_id


def test_token_limit_and_free_privacy_failures_are_actionable():
    with patch("openrouter_client.dotenv_values", return_value={"OPENROUTER_API_KEY": "secret", "OPENROUTER_MODEL": "nvidia/nemotron-3-ultra-550b-a55b:free"}), patch.dict("os.environ", {}, clear=True), patch("openrouter_client.urlopen") as send:
        with pytest.raises(OpenRouterError, match="fictional"): chat([{"role": "user", "content": "test"}])
        send.assert_not_called()
        send.return_value = io.BytesIO(b'{"choices":[{"finish_reason":"length","message":{"content":""}}]}')
        with pytest.raises(OpenRouterError, match="token limit"): chat([{"role": "user", "content": "test"}], synthetic=True)
        body = json.loads(send.call_args.args[0].data)
        assert body["reasoning"] == {"enabled": False, "exclude": True}
        assert "response_format" not in body


def test_category_totals_never_add_a_shared_return_twice():
    base = {"amount_type": "observed_prohibited_return", "currency": "MXN", "invoice_id": "a", "amount_centavos": 9000, "calculation": {"return_transaction_id": "same-bank-row"}}
    assert totals([base, {**base, "invoice_id": "b"}]) == {"observed_prohibited_return": {"MXN": 9000}}


def test_api_masked_citations_reveal_export_and_delete():
    client = TestClient(app)
    response = client.post("/api/datasets/demo", json={"seed": 187, "scenario": "all"})
    sid = response.json()["session_id"]
    assert response.json()["synthetic"]
    base = f"/api/datasets/{sid}"
    assert client.post(base+"/investigate", json={"mode": "offline"}).status_code == 200
    for _ in range(100):
        case = client.get(base+"/case").json()
        if case["status"] not in ("queued", "running"): break
        time.sleep(.01)
    assert case["status"] == "offline_complete"
    exported = client.get(base+"/export/json").json()
    ref = exported["findings"][0]["evidence"][0]
    assert ref in exported["source_evidence"]
    assert client.get(base+"/evidence", params={"ref": ref}).json()["id"] == ref
    original = client.get(base+"/evidence", params={"ref": ref, "reveal": True}).json()
    assert original["id"] != ref
    edge = next(edge for event in case["timeline"] for edge in event["result"].get("edges", []))
    graph_source = client.get(base+"/evidence", params={"ref": "bank:" + edge["id"]})
    assert graph_source.status_code == 200
    assert graph_source.json()["file"] == "bank.csv"
    assert "Investigation audit trail" in client.get(base+"/export/html").text
    assert client.delete(base).json()["status"] == "deleted"
    assert sid not in sessions
    assert client.get(base+"/case").status_code == 404


def test_uploaded_bundle_cannot_claim_trusted_synthetic_mode():
    client = TestClient(app)
    content = generate_scenario(187, "all")[0]
    info = client.post("/api/datasets/upload", files={"file": ("data.zip", content)}).json()
    assert not info["synthetic"]
    with patch("openrouter_client.dotenv_values", return_value={"OPENROUTER_API_KEY": "secret", "OPENROUTER_MODEL": "nvidia/nemotron-3-ultra-550b-a55b:free"}), patch.dict("os.environ", {}, clear=True):
        response = client.post(f"/api/datasets/{info['session_id']}/investigate", json={"mode": "ai"})
        assert response.status_code == 409


def test_hand_authored_revenue_fixture_without_generator():
    # Independent numeric oracle: 12,000 recorded less 2,000 reversed = 10,000 centavos.
    from forensic_auditor.data import SCHEMAS
    rows = {key: [] for key in SCHEMAS}
    rows["customers"] = [dict(version="2", id="buyer", name="Invented buyer", rfc="FICTIONAL")]
    rows["sales"] = [dict(version="2", id="sale", customer_id="buyer", company_id="seller", date="2026-08-12", period_start="2026-08-01", period_end="2026-08-10", currency="MXN", total="120.00", credit="20.00", status="active", recognition_condition="delivery", source_id="contract")]
    rows["sale_ledger"] = [dict(version="2", id="revenue", sale_id="sale", date="2026-08-12", currency="MXN", debit="20.00", credit="120.00", source_id="ledger")]
    rows["attestations"] = [dict(version="2", id=f"a{n}", subject_kind="sale", subject_id="sale", period_start="2026-08-01", period_end="2026-08-10", as_of="2026-08-12", status="not_delivered", issuer_id=f"observer{n}", source_id=f"inspection{n}") for n in (1, 2)]
    result = run(load_zip(pack(rows)))
    assert result["totals_by_category"] == {"revenue_overstatement": {"MXN": 10000}}
    assert "cannot substantiate" in answer(result, "Who is criminally guilty?")["answer"]


@pytest.mark.parametrize("scenario", ["service", "return", "sale"])
def test_serialized_finding_rejects_forged_amount_citation_and_claim(scenario):
    data = load_zip(generate_scenario(84911, scenario)[0])
    finding = run(data)["findings"][0]
    assert validate_scheme_finding(data, finding) == finding
    for field, value in (("amount_centavos", finding["amount_centavos"]+1), ("evidence", []), ("claim", "This supplier is guilty.")):
        forged = {**finding, field: value}
        with pytest.raises(ValueError): validate_scheme_finding(data, forged)


@pytest.mark.parametrize("mutation", ["disconnected", "time_reversed", "wrong_currency", "unknown_policy", "copied_link", "conflicting_owner"])
def test_prohibited_return_rejects_ambiguous_bank_or_relationship_evidence(mutation):
    data = load_zip(generate_scenario(84911, "return")[0])
    link = next(iter(data.tables["return_links"].values()))
    tid = link.return_transaction_id
    if mutation == "disconnected":
        data = mutate(data, "bank", lambda rows: [r.update(source_account=next(iter(data.tables["accounts"]))) for r in rows if r["id"] == tid])
    if mutation == "time_reversed":
        data = mutate(data, "bank", lambda rows: [r.update(timestamp="2026-01-01T00:00:00Z") for r in rows if r["id"] == tid])
    if mutation == "wrong_currency":
        data = mutate(data, "bank", lambda rows: [r.update(currency="USD") for r in rows if r["id"] == tid])
    if mutation == "unknown_policy":
        data = mutate(data, "return_policies", lambda rows: rows[0].update(disposition="unknown"))
    if mutation == "copied_link":
        data = mutate(data, "return_links", lambda rows: rows[1].update(source_id=rows[0]["source_id"]))
    if mutation == "conflicting_owner":
        data = mutate(data, "ownership", lambda rows: rows.append({**rows[0], "id": "conflict", "entity_id": "different-entity"}))
    assert not any(f["rule"] == "prohibited-return-v2" for f in run(data)["findings"])


def test_masking_preserves_schema_keys_numbers_and_derived_ids_in_answers():
    data = load_zip(generate_scenario(84771, "excess")[0])
    # Uploaded IDs may equal schema field names; masking must not rename API keys.
    data = mutate(data, "suppliers", lambda rows: rows[0].update(name="currency", rfc="secret-tax-1234"))
    case = run(data)
    presentation = Presentation(data)
    masked = presentation.apply(case)
    assert "currency" in masked["findings"][0]
    assert masked["findings"][0]["calculation"]["calculation"] == case["findings"][0]["calculation"]["calculation"]
    result = presentation.apply(answer(case, "What evidence supports the findings?"))
    assert case["findings"][0]["id"] not in result["answer"]
    assert "secret-tax-1234" not in json.dumps(export_case(data, case))


def test_selected_service_question_does_not_describe_unrelated_sales():
    case = run(load_zip(generate_scenario(723, "all")[0]))
    response = answer(case, "What evidence would change the service finding?")
    assert "Payment contrary" in response["answer"]
    assert "Revenue contrary" not in response["answer"]


def test_delete_during_inflight_call_cancels_then_releases_session():
    entered, release = threading.Event(), threading.Event()
    def slow(job):
        job.case["status"] = "running"
        entered.set()
        release.wait(3)
        job.case["status"] = "cancelled"
    client = TestClient(app)
    sid = client.post("/api/datasets/demo", json={"scenario": "cycle"}).json()["session_id"]
    base = f"/api/datasets/{sid}"
    with patch.object(Investigation, "run", slow):
        client.post(base+"/investigate", json={"mode": "offline"})
        assert entered.wait(1)
        assert client.delete(base).json()["status"] == "deleting"
        assert sessions[sid]["job"].cancelled.is_set()
        release.set()
        for _ in range(100):
            if sid not in sessions: break
            time.sleep(.01)
        assert sid not in sessions
