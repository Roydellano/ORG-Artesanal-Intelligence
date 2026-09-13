"""Bounded read-only ingestion; uploaded database objects are never executed."""
from collections import Counter
import csv
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import io
from pathlib import Path
import sqlite3
import zipfile

MAX_BYTES = 20_000_000
MAX_ROWS = 20_000
MAX_TEXT = 8000
TABLES = {
    'vendors': 'rfc legal_name registered_date address bank_clabe category contact_email',
    'invoices': 'uuid issuer_rfc receiver_rfc issue_date subtotal iva total concepto_text uso_cfdi forma_pago metodo_pago status',
    'ledger': 'entry_id date account_code account_name debit credit description invoice_uuid cost_center approver',
    'bank_txns': 'txn_id date from_clabe to_clabe amount reference channel',
    'purchase_orders': 'po_id vendor_rfc date amount requester approver description',
    'contracts': 'contract_id vendor_rfc start_date value scope_text',
    'employees': 'emp_id name role bank_clabe hire_date',
    'efos_list': 'rfc legal_name status publication_date',
}
IDS = {table: columns.split()[0] for table, columns in TABLES.items()}
AMOUNTS = {'invoices': 'total', 'bank_txns': 'amount', 'purchase_orders': 'amount', 'contracts': 'value'}
MONEY_FIELDS = {'subtotal', 'iva', 'total', 'debit', 'credit', 'amount', 'value'}
REQUIRED_MONEY = {'total', 'amount'}  # invoice totals and transfer/order amounts; other money may be NULL
DATE_FIELDS = {'date', 'issue_date', 'registered_date', 'start_date', 'hire_date', 'publication_date'}


def cents(value):
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number < 0 or number > 1_000_000_000 or number * 100 != (number * 100).to_integral_value():
            raise ValueError('Money must be nonnegative, finite pesos with at most two decimal places')
        return int(number * 100)
    except (InvalidOperation, TypeError):
        raise ValueError('Invalid monetary value') from None


def money(value):
    return float(Decimal(value) / 100)  # JSON boundary only; arithmetic stays integer.


@dataclass
class Estate:
    rows: dict
    identity: str
    content: bytes

    def row(self, table, record_id):
        return self.rows[table][str(record_id)]

    def evidence(self, table, record_id):
        return {'source_table': table, 'record_id': str(record_id), 'file_sha256': self.identity,
                'location': f'{table}.{IDS[table]}={record_id}', 'original': self.row(table, record_id),
                'ingestion_version': 'official-sqlite-v1'}


def load(content: bytes):
    if len(content) > MAX_BYTES or not content.startswith(b'SQLite format 3\x00'):
        raise ValueError('Provide a SQLite estate no larger than 20 MB')
    conn = sqlite3.connect(':memory:')
    try:
        conn.deserialize(content)
        conn.execute('PRAGMA trusted_schema=OFF')
        conn.execute('PRAGMA query_only=ON')
        ticks = [0]
        def bounded():
            ticks[0] += 1
            return ticks[0] > 2000
        conn.set_progress_handler(bounded, 1000)
        objects = {r[0]: (r[1], r[2] or '') for r in conn.execute('SELECT name,type,sql FROM sqlite_master')}
        rows, count = {}, 0
        for table, columns in TABLES.items():
            if table not in objects or objects[table][0] != 'table' or 'VIRTUAL' in objects[table][1].upper():
                raise ValueError(f'Missing ordinary table: {table}')
            fields = conn.execute(f'PRAGMA table_xinfo("{table}")').fetchall()
            have = {r[1] for r in fields if r[6] == 0}
            if not set(columns.split()) <= have:
                raise ValueError(f'{table}: missing required ordinary columns')
            names = columns.split()
            values = conn.execute(f'SELECT {",".join(names)} FROM "{table}" LIMIT {MAX_ROWS + 1}').fetchall()
            count += len(values)
            if count > MAX_ROWS:
                raise ValueError('Estate exceeds 20,000 records')
            rows[table] = {}
            for values_row in values:
                row = dict(zip(names, values_row))
                required_text = {'invoices': ('uuid', 'issuer_rfc', 'receiver_rfc', 'issue_date'),
                                 'bank_txns': ('txn_id', 'date', 'from_clabe', 'to_clabe'),
                                 'ledger': ('date',), 'purchase_orders': ('po_id', 'vendor_rfc', 'date'),
                                 'contracts': ('contract_id', 'vendor_rfc', 'start_date')}.get(table, ())
                if any(not isinstance(row[key], str) or not row[key].strip() for key in required_text):
                    raise ValueError(f'{table}: missing required identity/date')
                key = str(row[names[0]])
                if row[names[0]] is None or not key or key in rows[table]:
                    raise ValueError(f'{table}: missing or duplicate primary identity')
                for field, value in row.items():
                    if isinstance(value, bytes) or (isinstance(value, str) and len(value) > MAX_TEXT):
                        raise ValueError(f'{table}: invalid or oversized field')
                    if field in MONEY_FIELDS and (value is not None or field in REQUIRED_MONEY):
                        cents(value)
                    if field in DATE_FIELDS and value:
                        date.fromisoformat(str(value))
                if table == 'invoices' and row['status'] not in ('vigente', 'cancelado'):
                    raise ValueError('Invoice status must be vigente or cancelado')
                if table == 'efos_list' and row['status'] not in ('definitivo', 'presunto', 'desvirtuado', 'sentencia_favorable'):
                    raise ValueError('Unrecognized SAT status')
                rows[table][key] = row
            rows[table] = dict(sorted(rows[table].items()))
        return Estate(rows, hashlib.sha256(content).hexdigest(), content)
    except sqlite3.Error as error:
        raise ValueError('Invalid or over-budget SQLite estate') from error
    finally:
        conn.close()


def load_zip(content: bytes):
    """Convert the official estate_csv.zip (eight UTF-8 CSVs) into the same checked SQLite form.

    CLABEs, RFCs and ids stay text; empty cells become NULL. The replay archive stores the converted
    database, so later replays do not depend on the original ZIP bytes.
    """
    if len(content) > MAX_BYTES or not content.startswith(b'PK'):
        raise ValueError('Provide an estate_csv.zip no larger than 20 MB')
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        raise ValueError('Invalid estate ZIP') from None
    with archive:
        names = {Path(info.filename).name: info for info in archive.infolist() if not info.is_dir()}
        if sum(info.file_size for info in names.values()) > 4 * MAX_BYTES:
            raise ValueError('Estate ZIP expands beyond the size limit')
        conn = sqlite3.connect(':memory:')
        try:
            count = 0
            for table, columns in TABLES.items():
                names_list = columns.split()
                kinds = ['REAL' if c in MONEY_FIELDS else 'INTEGER' if c == 'entry_id' else 'TEXT' for c in names_list]
                conn.execute(f'CREATE TABLE {table} (' + ', '.join(f'{c} {k}' + (' PRIMARY KEY' if i == 0 else '')
                                                                  for i, (c, k) in enumerate(zip(names_list, kinds))) + ')')
                if f'{table}.csv' not in names:
                    raise ValueError(f'Estate ZIP is missing {table}.csv')
                text = archive.read(names[f'{table}.csv']).decode('utf-8-sig')
                reader = csv.DictReader(io.StringIO(text, newline=''))
                if not set(names_list) <= set(reader.fieldnames or []):
                    raise ValueError(f'{table}.csv: missing required columns')
                for row in reader:
                    count += 1
                    if count > MAX_ROWS:
                        raise ValueError('Estate exceeds 20,000 records')
                    values = []
                    for column, kind in zip(names_list, kinds):
                        value = (row.get(column) or '').strip()
                        if value == '':
                            values.append(None)
                        elif kind == 'REAL':
                            cents(value)
                            values.append(float(Decimal(value)))
                        elif kind == 'INTEGER':
                            values.append(int(value))
                        else:
                            values.append(value)
                    conn.execute(f'INSERT INTO {table} VALUES ({",".join("?" * len(values))})', values)
            conn.commit()
            serialized = conn.serialize()
        except (sqlite3.Error, UnicodeDecodeError, csv.Error) as error:
            raise ValueError('Invalid estate CSV content: ' + type(error).__name__) from None
        except (ValueError, InvalidOperation) as error:
            raise ValueError(str(error) or 'Invalid estate CSV value') from None
        finally:
            conn.close()
    return load(serialized)


def load_any(content: bytes):
    """Accept either judge format: SQLite estate.db or estate_csv.zip."""
    return load_zip(content) if content.startswith(b'PK') else load(content)


def infer_company(estate):
    """Audited company = the RFC on the most invoices (issuer or receiver). Ties break alphabetically."""
    counts = Counter()
    for invoice in estate.rows['invoices'].values():
        counts[invoice['issuer_rfc']] += 1
        counts[invoice['receiver_rfc']] += 1
    if not counts:
        raise ValueError('Cannot infer the audited company RFC from an estate without invoices; supply it explicitly')
    return min(counts, key=lambda rfc: (-counts[rfc], rfc))
