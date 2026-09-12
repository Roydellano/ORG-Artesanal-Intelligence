"""Strict CSV contracts, exact money and source-preserving ingestion."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import sqlite3
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Text = Annotated[str, Field(min_length=1, max_length=500)]
Money = Annotated[int, Field(ge=0, le=10**11)]


def centavos(value: str) -> int:
    if not re.fullmatch(r"\d{1,13}(\.\d{1,2})?", value):
        raise ValueError("Use a nonnegative decimal amount with at most two decimal places")
    try:
        return int(Decimal(value) * 100)
    except InvalidOperation:
        raise ValueError("Invalid amount") from None


def pesos(value: int, currency: str = "MXN") -> str:
    sign = "-" if value < 0 else ""
    value = abs(value)
    return f"{currency} {sign}${value // 100:,}.{value % 100:02d}"


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: Text


class Supplier(Record):
    rfc: Text
    name: Text

    @field_validator("rfc")
    @classmethod
    def normalize_rfc(cls, value):
        return value.strip().upper()


class Account(Record):
    entity_id: Text
    kind: Literal["company", "supplier", "other"]
    source: Text


class Invoice(Record):
    supplier_id: Text
    company_id: Text
    date: date
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    total: Money
    credit: Money
    status: Literal["active", "cancelled"]
    description: str = Field(max_length=2000)


class Bank(Record):
    timestamp: datetime
    source_account: Text
    destination_account: Text
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    amount: Annotated[int, Field(gt=0, le=10**11)]
    reference: str = Field(max_length=2000)

    @field_validator("timestamp")
    @classmethod
    def require_timezone(cls, value):
        if value.tzinfo is None:
            raise ValueError("Bank timestamps must include a UTC offset")
        return value


class Allocation(Record):
    transaction_id: Text
    invoice_id: Text
    amount: Annotated[int, Field(gt=0, le=10**11)]
    kind: Literal["payment", "refund"]


class Ledger(Record):
    invoice_id: Text
    date: date
    account: Text
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    debit: Money
    credit: Money


class Support(Record):
    invoice_id: Text
    status: Literal["delivered", "not_delivered", "unknown"]
    source: Text
    notes: str = Field(max_length=2000)


class Sat(Record):
    rfc: Text
    status: Literal["presunto", "definitivo", "desvirtuado", "sentencia_favorable"]
    publication_date: date
    snapshot_date: date
    source_url: Text

    @field_validator("rfc")
    @classmethod
    def normalize_rfc(cls, value):
        return value.strip().upper()


SCHEMAS = {"suppliers": Supplier, "accounts": Account, "invoices": Invoice,
           "bank": Bank, "allocations": Allocation, "ledger": Ledger,
           "support": Support, "sat": Sat}
MONEY_FIELDS = {"total", "credit", "amount", "debit"}
REQUIRED = {"suppliers", "accounts", "invoices", "bank", "allocations", "ledger"}


@dataclass(frozen=True)
class Dataset:
    identity: str
    tables: dict[str, dict[str, Record]]
    evidence: dict[str, dict]
    files: dict[str, bytes]
    warnings: list[str]

    def ref(self, table: str, record_id: str) -> str:
        return f"{table}:{record_id}"

    def refs(self, table: str) -> list[str]:
        return [self.ref(table, key) for key in self.tables[table]]

    def retrieve(self, refs: list[str]) -> list[dict]:
        return [self.evidence[ref] for ref in refs]


def load_zip(content: bytes) -> Dataset:
    """Never extract uploaded paths; reject unknown members and oversized archives."""
    if len(content) > 20_000_000:
        raise ValueError("Upload limit is 20 MB")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = archive.infolist()
            allowed = {f"{name}.csv" for name in SCHEMAS}
            if len(members) > len(allowed) or len({m.filename for m in members}) != len(members):
                raise ValueError("Duplicate or excessive ZIP members")
            if any(m.filename not in allowed or m.flag_bits & 1 for m in members):
                raise ValueError("ZIP must contain only the documented CSV filenames at its root")
            if sum(m.file_size for m in members) > 20_000_000:
                raise ValueError("Uncompressed dataset limit is 20 MB")
            return load_files({m.filename: archive.read(m) for m in members})
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError):
        raise ValueError("Invalid or unsupported ZIP file") from None


def load_files(files: dict[str, bytes]) -> Dataset:
    names = {f"{name}.csv" for name in SCHEMAS}
    if set(files) - names or not {f"{t}.csv" for t in REQUIRED} <= set(files):
        raise ValueError("Required CSV files missing or unknown filenames supplied")
    if sum(map(len, files.values())) > 20_000_000:
        raise ValueError("Dataset limit is 20 MB")
    hashes = {name: hashlib.sha256(value).hexdigest() for name, value in sorted(files.items())}
    identity = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    tables = {name: {} for name in SCHEMAS}
    evidence = {}
    for filename, content in sorted(files.items()):
        table = filename[:-4]
        schema = SCHEMAS[table]
        try:
            reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig"), newline=""))
            if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
                raise ValueError("Missing or duplicate column names")
            if set(reader.fieldnames) != set(schema.model_fields):
                raise ValueError(f"Expected columns: {', '.join(schema.model_fields)}")
            for row_number, raw in enumerate(reader, 2):
                if len(evidence) >= 20_000:
                    raise ValueError("Limit is 20,000 total records")
                if None in raw or any(value is None for value in raw.values()):
                    raise ValueError(f"Malformed CSV record {row_number}")
                normalized = {key: value.strip() for key, value in raw.items()}
                for key in MONEY_FIELDS & normalized.keys():
                    normalized[key] = centavos(normalized[key])
                row = schema.model_validate(normalized)
                if row.id in tables[table]:
                    raise ValueError(f"Duplicate {table} ID at record {row_number}")
                tables[table][row.id] = row
                ref = f"{table}:{row.id}"
                evidence[ref] = {"id": ref, "file": filename, "sha256": hashes[filename],
                                 "csv_record": row_number, "line_end": reader.line_num,
                                 "original": raw, "normalized": row.model_dump(mode="json"),
                                 "ingestion_version": "csv-v1"}
        except (ValueError, UnicodeError, csv.Error) as exc:
            # Pydantic errors may echo uploaded text; show only a controlled location.
            if type(exc).__name__ == "ValidationError":
                detail = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['type']}" for e in exc.errors())
            else:
                detail = str(exc)
            raise ValueError(f"{filename}: {detail}") from None
    warnings = validate_links(tables)
    return Dataset(identity, tables, evidence, dict(files), warnings)


def validate_links(tables: dict) -> list[str]:
    warnings = []
    for invoice in tables["invoices"].values():
        if invoice.supplier_id not in tables["suppliers"] or invoice.credit > invoice.total:
            raise ValueError("Invoice supplier is missing or credit exceeds total")
    totals = {}
    pairs = set()
    for item in tables["allocations"].values():
        tx = tables["bank"].get(item.transaction_id)
        invoice = tables["invoices"].get(item.invoice_id)
        if not tx or not invoice or tx.currency != invoice.currency:
            raise ValueError("Allocation has a missing reference or currency mismatch")
        pair = (tx.id, invoice.id)
        if pair in pairs:
            raise ValueError("Duplicate transaction/invoice allocation")
        pairs.add(pair)
        totals[tx.id] = totals.get(tx.id, 0) + item.amount
        if totals[tx.id] > tx.amount:
            raise ValueError("Allocations exceed a bank transaction amount")
    for table in ("ledger", "support"):
        for row in tables[table].values():
            if row.invoice_id not in tables["invoices"]:
                raise ValueError(f"{table} references a missing invoice")
    for row in tables["sat"].values():
        if row.publication_date > row.snapshot_date:
            raise ValueError("SAT publication cannot follow its snapshot date")
    for tx in tables["bank"].values():
        if tx.source_account not in tables["accounts"] or tx.destination_account not in tables["accounts"]:
            warnings.append(f"Unknown account ownership on bank:{tx.id}; related findings will abstain.")
    remaining = sum(tx.amount != totals.get(tx.id, 0) for tx in tables["bank"].values())
    if remaining:
        warnings.append(f"{remaining} bank transactions have unallocated amounts; linked suppliers require review.")
    for optional in ("support", "sat"):
        if not tables[optional]:
            warnings.append(f"No {optional} records supplied.")
    if not tables["invoices"]:
        warnings.append("No invoices supplied; reconciliation coverage is empty.")
    return warnings


def persist(dataset: Dataset, path: str) -> None:
    """Optional local archive with parameterized writes and dataset-scoped keys."""
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS evidence (dataset TEXT, id TEXT, body TEXT, PRIMARY KEY(dataset,id))")
        connection.executemany("INSERT OR REPLACE INTO evidence VALUES (?,?,?)", [
            (dataset.identity, key, json.dumps(value)) for key, value in dataset.evidence.items()])
