"""Optional Tiger Data (PostgreSQL) archive of completed analyses.

Only masked case views are written. Original record values, source bytes, replay
bundles and Q&A text stay local. Disabled unless TIGER_DATABASE_URL is set.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from uuid import UUID

from dotenv import dotenv_values

SCHEMA_VERSION = "analyses-v1"
_ready = threading.Lock()
_initialized: set[str] = set()
last_error: str | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    kind TEXT NOT NULL CHECK (kind IN ('csv', 'official')),
    dataset_sha256 TEXT NOT NULL,
    status TEXT NOT NULL,
    mode TEXT,
    model TEXT,
    synthetic BOOLEAN NOT NULL DEFAULT false,
    findings_count INTEGER NOT NULL,
    leads_count INTEGER NOT NULL,
    totals JSONB NOT NULL,
    masked_case JSONB NOT NULL,
    schema_version TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS analyses_created_at_idx ON analyses (created_at DESC);
CREATE INDEX IF NOT EXISTS analyses_dataset_idx ON analyses (dataset_sha256, created_at DESC);
"""
SUMMARY_COLUMNS = "id, created_at, kind, dataset_sha256, status, mode, model, synthetic, findings_count, leads_count, totals"


class StorageError(RuntimeError):
    """Safe error for callers; never includes the connection string."""


def database_url() -> str:
    config = {**dotenv_values(Path(__file__).resolve().parents[1] / ".env"), **os.environ}
    return (config.get("TIGER_DATABASE_URL") or "").strip()


def enabled() -> bool:
    return bool(database_url())


def status() -> dict:
    return {"enabled": enabled(), "last_error": last_error, "stores": "masked case views only"}


def _connect():
    url = database_url()
    if not url:
        raise StorageError("Set TIGER_DATABASE_URL in the server .env to save analyses.")
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError:
        raise StorageError("Install psycopg to use Tiger Data storage: pip install -r requirements.txt") from None
    try:
        connection = psycopg.connect(url, connect_timeout=10, row_factory=dict_row)
        with _ready:
            if url not in _initialized:
                with connection.transaction():
                    connection.execute(SCHEMA)
                _initialized.add(url)
        return connection
    except psycopg.Error as error:
        raise StorageError(f"Tiger Data connection failed ({type(error).__name__}). Check TIGER_DATABASE_URL and network access.") from None


def summarize(kind: str, masked_case: dict, *, synthetic: bool = False) -> dict:
    """Index columns come from the masked view, so they cannot hold original identities."""
    if kind == "csv":
        return {"dataset_sha256": masked_case["dataset_id"], "status": masked_case["status"],
                "mode": masked_case.get("mode"), "model": masked_case.get("model"), "synthetic": synthetic,
                "findings_count": len(masked_case.get("findings", [])), "leads_count": len(masked_case.get("leads", [])),
                "totals": masked_case.get("totals", {})}
    if kind == "official":
        metadata = masked_case.get("run_metadata", {})
        findings = masked_case.get("findings", [])
        return {"dataset_sha256": masked_case["estate_sha256"], "status": masked_case["status"],
                "mode": metadata.get("mode"), "model": metadata.get("model"), "synthetic": synthetic,
                "findings_count": len(findings), "leads_count": len(masked_case.get("leads_not_pursued", [])) + len(findings),
                "totals": {"schemes": sorted({f["scheme_type"] for f in findings}), "mxn_cost": metadata.get("mxn_cost")}}
    raise ValueError("Unknown analysis kind")


def save(kind: str, masked_case: dict, *, synthetic: bool = False) -> str:
    row = summarize(kind, masked_case, synthetic=synthetic)
    with _connect() as connection:
        record = connection.execute(
            "INSERT INTO analyses (kind, dataset_sha256, status, mode, model, synthetic, findings_count, leads_count, totals, masked_case, schema_version) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s) RETURNING id",
            (kind, row["dataset_sha256"], row["status"], row["mode"], row["model"], row["synthetic"],
             row["findings_count"], row["leads_count"], json.dumps(row["totals"]),
             json.dumps(masked_case, ensure_ascii=False, allow_nan=False), SCHEMA_VERSION)).fetchone()
    return str(record["id"])


def archive(kind: str, masked_case: dict, *, synthetic: bool = False) -> str | None:
    """Best-effort save for background jobs: a storage outage never changes the investigation."""
    global last_error
    if not enabled():
        return None
    try:
        identity = save(kind, masked_case, synthetic=synthetic)
        last_error = None
        return identity
    except StorageError as error:
        last_error = str(error)
    except Exception as error:  # noqa: BLE001 - report the type only; values may be sensitive
        last_error = f"Saving the analysis failed ({type(error).__name__})."
    return None


def _serialize(row: dict) -> dict:
    return {**row, "id": str(row["id"]), "created_at": row["created_at"].isoformat()}


def list_analyses(limit: int = 50, dataset_sha256: str | None = None) -> list[dict]:
    query = f"SELECT {SUMMARY_COLUMNS} FROM analyses"
    parameters: tuple = ()
    if dataset_sha256:
        query += " WHERE dataset_sha256 = %s"
        parameters = (dataset_sha256,)
    with _connect() as connection:
        rows = connection.execute(query + " ORDER BY created_at DESC LIMIT %s", (*parameters, limit)).fetchall()
    return [_serialize(row) for row in rows]


def get_analysis(identity: str) -> dict | None:
    UUID(identity)
    with _connect() as connection:
        row = connection.execute(f"SELECT {SUMMARY_COLUMNS}, masked_case FROM analyses WHERE id = %s", (identity,)).fetchone()
    return _serialize(row) if row else None


def delete_analysis(identity: str) -> bool:
    UUID(identity)
    with _connect() as connection:
        return connection.execute("DELETE FROM analyses WHERE id = %s", (identity,)).rowcount == 1
