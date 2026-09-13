import json
import os
import re
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from forensic_auditor import storage
from forensic_auditor.api import app, sessions
from tools.official_generate import generate, COMPANY


def wait_for(captured, count=1):
    for _ in range(300):
        if len(captured) >= count:
            return captured
        time.sleep(.02)
    raise AssertionError("Analysis was not archived")


def test_disabled_storage_lists_nothing_and_never_connects():
    with patch.object(storage, "database_url", return_value=""), patch.object(storage, "_connect") as connect:
        body = TestClient(app).get("/api/analyses").json()
        assert body["enabled"] is False and body["items"] == []
        assert storage.archive("csv", {"dataset_id": "x", "status": "offline_complete"}) is None
        connect.assert_not_called()


def test_csv_investigation_archives_only_masked_view():
    captured = []
    client = TestClient(app)
    with patch.object(storage, "enabled", return_value=True), \
            patch.object(storage, "save", side_effect=lambda kind, case, **kw: captured.append((kind, case, kw)) or "id"):
        response = client.post("/api/datasets/demo", json={"seed": 101, "scenario": "all"})
        sid = response.json()["session_id"]
        try:
            assert client.post(f"/api/datasets/{sid}/investigate", json={"mode": "offline"}).status_code == 200
            kind, case, options = wait_for(captured)[0]
            data = sessions[sid]["data"]
        finally:
            client.delete(f"/api/datasets/{sid}")
    assert kind == "csv" and options == {"synthetic": True}
    assert case["status"] == "offline_complete" and case["findings"]
    assert storage.summarize("csv", case)["dataset_sha256"] == data.identity
    text = json.dumps(case, ensure_ascii=False)
    originals = {value for record in data.evidence.values() for key, value in record["original"].items()
                 if key in {"name", "rfc", "supplier_name"} and isinstance(value, str) and len(value) >= 4}
    assert originals
    assert not [value for value in originals if re.search(r"(?<![\w-])" + re.escape(value) + r"(?![\w-])", text)]


def test_official_investigation_archives_only_masked_view(tmp_path):
    path = tmp_path / "estate.db"
    generate(101, path)
    captured = []
    client = TestClient(app)
    with patch.object(storage, "enabled", return_value=True), \
            patch.object(storage, "save", side_effect=lambda kind, case, **kw: captured.append((kind, case)) or "id"):
        response = client.post("/api/estates/upload", params={"seed": 101, "company_rfc": COMPANY},
                               files={"file": ("estate.db", path.read_bytes())})
        base = "/api/estates/" + response.json()["session_id"]
        try:
            assert client.post(base + "/run").is_success
            kind, case = wait_for(captured)[0]
        finally:
            client.delete(base)
    assert kind == "official" and len(case["findings"]) == 5
    assert COMPANY not in json.dumps(case, ensure_ascii=False)
    summary = storage.summarize("official", case)
    assert summary["findings_count"] == 5 and len(summary["totals"]["schemes"]) == 5


def test_archive_failure_is_reported_without_changing_the_case():
    with patch.object(storage, "enabled", return_value=True), \
            patch.object(storage, "save", side_effect=storage.StorageError("Tiger Data connection failed (OperationalError).")):
        assert storage.archive("csv", {"dataset_id": "x"}) is None
        assert storage.status()["last_error"].startswith("Tiger Data connection failed")
    with patch.object(storage, "enabled", return_value=True), patch.object(storage, "save", return_value="id"):
        storage.archive("csv", {})
        assert storage.status()["last_error"] is None


def test_saved_analysis_endpoints():
    client = TestClient(app)
    assert client.get("/api/analyses/not-a-uuid").status_code == 422
    identity = "00000000-0000-4000-8000-000000000001"
    with patch.object(storage, "_connect", side_effect=storage.StorageError("unavailable")):
        assert client.get(f"/api/analyses/{identity}").status_code == 502
    with patch.object(storage, "get_analysis", return_value=None), patch.object(storage, "delete_analysis", return_value=False):
        assert client.get(f"/api/analyses/{identity}").status_code == 404
        assert client.delete(f"/api/analyses/{identity}").status_code == 404
    with patch.object(storage, "enabled", return_value=True), \
            patch.object(storage, "list_analyses", return_value=[{"id": identity}]) as listing:
        assert client.get("/api/analyses?limit=5").json()["items"] == [{"id": identity}]
        listing.assert_called_once_with(5, None)


@pytest.mark.skipif(not os.environ.get("TIGER_TEST_DATABASE_URL"), reason="Set TIGER_TEST_DATABASE_URL to run against a real Tiger Data service")
def test_round_trip_against_tiger_data(monkeypatch):
    monkeypatch.setenv("TIGER_DATABASE_URL", os.environ["TIGER_TEST_DATABASE_URL"])
    case = {"dataset_id": "test-" + os.urandom(8).hex(), "status": "offline_complete", "mode": "offline",
            "findings": [{"id": "R-1"}], "leads": [], "totals": {"MXN": 125}}
    identity = storage.save("csv", case)
    try:
        assert storage.list_analyses(5, case["dataset_id"])[0]["id"] == identity
        row = storage.get_analysis(identity)
        assert row["masked_case"] == case and row["totals"] == {"MXN": 125}
    finally:
        assert storage.delete_analysis(identity)
    assert storage.get_analysis(identity) is None
