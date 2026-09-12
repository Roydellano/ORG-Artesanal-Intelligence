"""Independent fictional official estates and separately written evaluator answer keys."""
import argparse
from datetime import date, timedelta
import json
from pathlib import Path
import random
import sqlite3

SCHEMA = Path(__file__).resolve().parents[1] / 'specs/student-materials/forensic-auditor/estate_schema.sql'
TYPES = ['phantom_vendor', 'kickback', 'round_tripping', 'threshold_splitting', 'revenue_inflation']
COMPANY = 'EMP920101AB1'


def generate(seed, path, *, clean=False, scheme_types=None):
    rng = random.Random(seed)
    conn = sqlite3.connect(':memory:')
    conn.executescript(SCHEMA.read_text(encoding='utf-8'))  # Trusted checked-in schema, never uploaded SQL.
    truth = {'seed': seed, 'company_rfc': COMPANY, 'schemes': [], 'decoys': []}
    used = set()
    def uid(prefix):
        while True:
            value = prefix + str(rng.randrange(10**8, 10**9))
            if value not in used:
                used.add(value)
                return value
    def insert(table, **row):
        conn.execute(f'INSERT INTO {table} ({",".join(row)}) VALUES ({",".join("?" for _ in row)})', list(row.values()))
    def vendor(rfc=None):
        rfc = rfc or uid('FIC')
        account = f'{rng.randrange(10**17, 10**18):018d}'
        insert('vendors', rfc=rfc, legal_name='Entidad Ficticia ' + uid('N'), registered_date='2023-01-01',
               address='Domicilio ficticio', bank_clabe=account, category='Servicios', contact_email='fictional@example.invalid')
        return rfc, account
    _, company_account = vendor(COMPANY)
    shared = vendor()
    def amount():
        return rng.randrange(100_000, 4_000_000) / 100
    def invoice(v, total, *, sales=False, cancelled=False, day=None):
        iid = uid('INV-')
        day = day or (date(2026, 2, 1) + timedelta(days=rng.randrange(20))).isoformat()
        insert('invoices', uuid=iid, issuer_rfc=COMPANY if sales else v[0], receiver_rfc=v[0] if sales else COMPANY,
               issue_date=day, subtotal=total, iva=0, total=total, concepto_text='Servicio ficticio según contrato',
               uso_cfdi='G03', forma_pago='03', metodo_pago='PUE', status='cancelado' if cancelled else 'vigente')
        # Balanced GL: separate revenue/expense from balancing accounts.
        for account, name, debit, credit in ([('4000', 'Ingresos', 0, total), ('1100', 'Clientes', total, 0)] if sales else
                                             [('5000', 'Gastos', total, 0), ('2100', 'Proveedores', 0, total)]):
            insert('ledger', date=day, account_code=account, account_name=name, debit=debit, credit=credit,
                   description='Registro contable ficticio', invoice_uuid=iid, cost_center='Centro ficticio', approver='Contabilidad')
        return iid, day
    def transfer(source, destination, total, day, iid):
        tid = uid('BNK-')
        insert('bank_txns', txn_id=tid, date=day, from_clabe=source, to_clabe=destination, amount=total, reference=iid, channel='SPEI')
        return tid
    def contract(v, total, payload):
        insert('contracts', contract_id=uid('CTR-'), vendor_rfc=v[0], start_date='2026-01-01', value=total,
               scope_text=json.dumps({'valid_until': '2026-12-31', **payload}))
    def build(kind, benign, v):
        total = amount()
        if kind == 'threshold_splitting':
            limit = 10000
            count = rng.randrange(3, 6)
            each = rng.randrange(400000, 700000) / 100
            total = round(each * count, 2)
            contract(v, total, {'type': 'purchase_policy', 'approval_limit_pesos': str(limit),
                               'authorized_approvers': ['Director autorizado'], 'aggregation_days': 7})
            for _ in range(count):
                insert('purchase_orders', po_id=uid('PO-'), vendor_rfc=v[0], date='2026-03-10', amount=each,
                       requester='Solicitante ' + v[0], approver='Director autorizado' if benign else 'Solicitante local', description='Mismo proyecto documentado')
            return total, [], [], ['RFC:' + v[0]]
        iid, day = invoice(v, total, sales=kind == 'revenue_inflation', cancelled=kind == 'revenue_inflation')
        txns = []
        entities = ['RFC:' + v[0]]
        if kind == 'revenue_inflation':
            entities = ['RFC:' + COMPANY]
            if benign:
                insert('ledger', date=day, account_code='4000', account_name='Ingresos', debit=total, credit=0,
                       description='Reversión de cancelación', invoice_uuid=iid, cost_center='Centro ficticio', approver='Contabilidad')
            return total, [iid], txns, entities
        txns.append(transfer(company_account, v[1], total, day, iid))
        if kind == 'phantom_vendor':
            contract(v, total, {'type': 'delivery_terms', 'invoice_uuid': iid, 'payment_condition': 'delivery',
                               'witnesses': [{'author': 'Inspector ' + uid('A'), 'delivered': benign, 'date': '2026-03-01'},
                                             {'author': 'Revisor ' + uid('B'), 'delivered': benign, 'date': '2026-03-01'}]})
            insert('efos_list', rfc=v[0], legal_name='Entidad ficticia', status='presunto' if benign else 'definitivo', publication_date='2026-01-01')
        else:
            if kind == 'kickback':
                emp = uid('EMP:')
                end = f'{rng.randrange(10**17, 10**18):018d}'
                insert('employees', emp_id=emp, name='Empleado ficticio', role='Compras', bank_clabe=end, hire_date='2020-01-01')
                entities.append(emp)
                contract(v, total, {'type': 'payment_policy', 'invoice_uuid': iid, 'employee_benefits': 'permitted' if benign else 'prohibited'})
            else:
                end = company_account
                contract(v, total, {'type': 'funding_terms', 'invoice_uuid': iid, 'commercial_purpose': 'loan' if benign else 'none'})
            current = v[1]
            # Two to four hops with varied intermediate fictional entities.
            for n in range(rng.randrange(0, 3)):
                intermediary = vendor()
                next_day = (date.fromisoformat(day) + timedelta(days=len(txns))).isoformat()
                txns.append(transfer(current, intermediary[1], total, next_day, iid))
                current = intermediary[1]
            next_day = (date.fromisoformat(day) + timedelta(days=len(txns))).isoformat()
            txns.append(transfer(current, end, total if kind == 'round_tripping' else round(total / 10, 2), next_day, iid))
        return total, [iid], txns, entities
    if not clean:
        for kind in (scheme_types if scheme_types is not None else TYPES):
            v = shared if kind in ('phantom_vendor', 'kickback') else vendor()
            total, invoices, txns, entities = build(kind, False, v)
            truth['schemes'].append({'scheme_id': uid('S-'), 'type': kind, 'entities': entities, 'peso_amount': total,
                                    'supporting_invoices': invoices, 'supporting_txns': txns, 'difficulty': 'hard' if v == shared else 'medium'})
    for n in range(10):
        kind = TYPES[n % len(TYPES)]
        v = vendor()
        _, invoices, _, entities = build(kind, True, v)
        # A cancelled/reversed sale is company evidence, not an accusation against its customer.
        truth['decoys'].append({'entity': 'RFC:' + v[0], 'signal': kind,
                                'why_innocent': {'phantom_vendor': 'Contract witnesses document delivery despite SAT signal.',
                                                'kickback': 'Supplied contract expressly permits the employee benefit.',
                                                'round_tripping': 'Supplied funding terms document a loan.',
                                                'threshold_splitting': 'Required director approved the aggregated purchases.',
                                                'revenue_inflation': 'Linked revenue debit fully reverses the cancelled invoice.'}[kind],
                                'invoices': invoices})
    conn.commit()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(conn.serialize())
    conn.close()
    return truth


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--seed', type=int, required=True)
    parser.add_argument('--estate', type=Path, required=True)
    parser.add_argument('--answer-key', type=Path, required=True)
    parser.add_argument('--clean', action='store_true')
    args = parser.parse_args()
    truth = generate(args.seed, args.estate, clean=args.clean)
    args.answer_key.parent.mkdir(parents=True, exist_ok=True)
    args.answer_key.write_text(json.dumps(truth, indent=2), encoding='utf-8')
    print(f'Fictional estate written to {args.estate}; company RFC {COMPANY}. Answer key remains evaluator-only.')
