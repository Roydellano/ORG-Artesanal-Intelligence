"""Independent fictional official estates and separately written evaluator answer keys.

Two styles, both conforming to specs/student-materials/forensic-auditor/estate_schema.sql:

* ``records`` (default) - judge-like. Ordinary company activity (purchases with POs, payroll, sales and
  collections, prose contracts), a company that is NOT in the vendors table, and schemes and decoys expressed
  only through the eight official tables.
* ``typed`` - the optional typed-contract convention read by the documentary predicates.

The answer key is written to a separate file for the evaluator. The runtime never imports this module.
"""
import argparse
import csv
from datetime import date, timedelta
import io
import json
import math
from pathlib import Path
import random
import sqlite3
import zipfile

SCHEMA = Path(__file__).resolve().parents[1] / 'specs/student-materials/forensic-auditor/estate_schema.sql'
TYPES = ['phantom_vendor', 'kickback', 'round_tripping', 'threshold_splitting', 'revenue_inflation']
COMPANY = 'EMP920101AB1'
TABLE_ORDER = ['vendors', 'invoices', 'ledger', 'bank_txns', 'purchase_orders', 'contracts', 'employees', 'efos_list']
MONEY = {'subtotal', 'iva', 'total', 'debit', 'credit', 'amount', 'value'}
START = date(2026, 1, 1)
PERIOD_DAYS = 180
BANKS = ['002', '012', '014', '021', '030', '036', '044', '058', '072', '127', '137']
LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
FIRST = ['Ana', 'Luis', 'María', 'José', 'Carmen', 'Jorge', 'Lucía', 'Ricardo', 'Sofía', 'Diego', 'Elena', 'Fernando',
         'Patricia', 'Andrés', 'Gabriela', 'Héctor', 'Mónica', 'Raúl', 'Verónica', 'Tomás', 'Adriana', 'Emilio']
LAST = ['García', 'Hernández', 'López', 'Martínez', 'González', 'Pérez', 'Rodríguez', 'Sánchez', 'Ramírez', 'Torres',
        'Flores', 'Rivera', 'Gómez', 'Díaz', 'Cruz', 'Morales', 'Reyes', 'Gutiérrez', 'Ortiz', 'Castillo']
WORDS = ['Norte', 'Sierra', 'Alfa', 'Delta', 'Cumbre', 'Río', 'Nova', 'Vértice', 'Brava', 'Puente', 'Aurora', 'Roble',
         'Faro', 'Mirador', 'Cobalto', 'Nexo', 'Prisma', 'Atlas', 'Cima', 'Horizonte']
CATEGORIES = [('Mantenimiento', 'Mantenimiento de equipo industrial'), ('Logística', 'Servicio de transporte de mercancía'),
              ('Consultoría', 'Servicios de consultoría administrativa'), ('Limpieza', 'Servicio de limpieza de instalaciones'),
              ('Tecnología', 'Licencias y soporte de software'), ('Seguridad', 'Servicio de vigilancia'),
              ('Materiales', 'Suministro de materia prima'), ('Publicidad', 'Campaña publicitaria')]


def day(offset):
    return (START + timedelta(days=int(offset))).isoformat()


class Builder:
    def __init__(self, seed):
        self.rng = random.Random(seed)
        self.conn = sqlite3.connect(':memory:')
        self.conn.executescript(SCHEMA.read_text(encoding='utf-8'))  # Trusted checked-in schema, never uploaded SQL.
        self.used = set()
        self.entry = 0

    def unique(self, make):
        while True:
            value = make()
            if value not in self.used:
                self.used.add(value)
                return value

    def rfc(self, person=False):
        rng = self.rng
        return self.unique(lambda: ''.join(rng.choice(LETTERS) for _ in range(4 if person else 3))
                           + f'{rng.randrange(55, 99):02d}{rng.randrange(1, 13):02d}{rng.randrange(1, 29):02d}'
                           + ''.join(rng.choice(LETTERS + '0123456789') for _ in range(3)))

    def clabe(self, bank=None):
        rng = self.rng
        return self.unique(lambda: (bank or rng.choice(BANKS)) + f'{rng.randrange(10**14, 10**15)}')

    def ident(self, prefix):
        return self.unique(lambda: f'{prefix}-{self.rng.randrange(10**6, 10**7)}')

    def insert(self, table, **row):
        self.conn.execute(f'INSERT INTO {table} ({",".join(row)}) VALUES ({",".join("?" for _ in row)})', list(row.values()))
        return row

    def person(self):
        return f'{self.rng.choice(FIRST)} {self.rng.choice(LAST)} {self.rng.choice(LAST)}'

    def vendor(self, category='Servicios', registered=None, *, email=True, address=True, clabe=None, name=None):
        rfc = self.rfc()
        name = name or f'{self.rng.choice(WORDS)} {self.rng.choice(WORDS)} {category} SA de CV'
        return self.insert('vendors', rfc=rfc, legal_name=name, registered_date=registered or day(-self.rng.randrange(400, 3000)),
                           address=f'Calle {self.rng.choice(WORDS)} {self.rng.randrange(10, 999)}, Monterrey' if address else None,
                           bank_clabe=clabe or self.clabe(), category=category,
                           contact_email=f'contacto{self.rng.randrange(100, 999)}@{name.split()[0].lower()}.example.mx' if email else None)

    def ledger(self, when, code, name, debit, credit, description, invoice, approver):
        self.entry += 1
        self.insert('ledger', entry_id=self.entry, date=when, account_code=code, account_name=name, debit=debit, credit=credit,
                    description=description, invoice_uuid=invoice, cost_center='CC-100 Operación', approver=approver)

    def invoice(self, issuer, receiver, when, total, concept, *, sale=False, metodo='PUE', status='vigente', approver='Contabilidad'):
        uuid = self.ident('INV')
        subtotal = round(total / 1.16, 2)
        self.insert('invoices', uuid=uuid, issuer_rfc=issuer, receiver_rfc=receiver, issue_date=when, subtotal=subtotal,
                    iva=round(total - subtotal, 2), total=total, concepto_text=concept, uso_cfdi='G03' if not sale else 'G01',
                    forma_pago='03' if metodo == 'PUE' else '99', metodo_pago=metodo, status=status)
        if sale:
            self.ledger(when, '1100', 'Clientes', total, 0, 'Registro venta', uuid, approver)
            self.ledger(when, '4000', 'Ingresos', 0, total, 'Registro venta', uuid, approver)
        else:
            self.ledger(when, '5000', 'Gastos operativos', total, 0, 'Registro factura', uuid, approver)
            self.ledger(when, '2100', 'Proveedores', 0, total, 'Registro factura', uuid, approver)
        return uuid

    def transfer(self, source, destination, amount, when, reference, channel='SPEI'):
        tid = self.ident('BNK')
        self.insert('bank_txns', txn_id=tid, date=when, from_clabe=source, to_clabe=destination, amount=round(amount, 2),
                    reference=reference, channel=channel)
        return tid

    def serialize(self, path):
        self.conn.commit()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.conn.serialize())
        self.conn.close()


def generate_records(seed, path, *, clean=False, scheme_types=None):
    b = Builder(seed)
    rng = b.rng
    company = b.rfc()
    company_clabe = b.clabe()
    truth = {'seed': seed, 'company_rfc': company, 'schemes': [], 'decoys': []}
    limit = rng.choice([50_000, 100_000, 250_000])
    end = PERIOD_DAYS - 1

    roles = ['Director de Finanzas', 'Director de Operaciones', 'Gerente de Compras', 'Gerente de Mantenimiento', 'Jefe de Almacén',
             'Analista de Compras', 'Contador General', 'Auxiliar Contable', 'Supervisor de Planta', 'Ingeniero de Procesos']
    employees = []
    for i in range(rng.randrange(22, 34)):
        employee = b.insert('employees', emp_id=b.unique(lambda: f'EMP:{rng.randrange(1000, 9999)}'), name=b.person(),
                            role=roles[i] if i < len(roles) else rng.choice(roles[5:]), bank_clabe=b.clabe(),
                            hire_date=day(-rng.randrange(200, 4000)))
        employees.append(employee)
    seniors = [e for e in employees if e['role'].startswith('Director')]
    juniors = [e for e in employees if e['role'].startswith(('Gerente', 'Jefe'))]
    requesters = [e for e in employees if not e['role'].startswith('Director')]
    accountants = [e['name'] for e in employees if 'Conta' in e['role']]
    for month in range(1, 7):
        for e in employees:
            b.transfer(company_clabe, e['bank_clabe'], rng.randrange(18_000, 90_000), f'2026-{month:02d}-28', f'Nómina 2026-{month:02d}')

    def purchase(vendor, when, amount, *, requester=None, approver=None, description=None, po=True, reference=True, pay=True, metodo='PUE'):
        category = next((c for c in CATEGORIES if c[0] == vendor['category']), CATEGORIES[0])
        requester = requester or rng.choice(requesters)['name']
        approver = approver or (rng.choice(seniors)['name'] if amount >= limit else rng.choice(juniors)['name'])
        po_id = None
        if po:
            po_id = b.ident('PO')
            b.insert('purchase_orders', po_id=po_id, vendor_rfc=vendor['rfc'], date=day(when), amount=amount, requester=requester,
                     approver=approver, description=description or category[1])
        invoice_day = min(when + rng.randrange(1, 8), end)
        uuid = b.invoice(vendor['rfc'], company, day(invoice_day), amount, description or category[1], metodo=metodo, approver=rng.choice(accountants))
        txn, paid_day = None, invoice_day + rng.randrange(2, 30)
        if pay and paid_day <= end:
            txn = b.transfer(company_clabe, vendor['bank_clabe'], amount, day(paid_day),
                             f'Pago factura {uuid}' if reference else rng.choice(['Pago proveedor', 'Transferencia', '']))
        return {'po': po_id, 'invoice': uuid, 'txn': txn, 'paid_day': paid_day if txn else None}

    def background_amount():
        return round(max(1_500, min(limit * 3, rng.lognormvariate(math.log(limit * 0.18), 0.9))), 2)

    honest = []
    for _ in range(rng.randrange(28, 40)):
        category = rng.choice(CATEGORIES)
        vendor = b.vendor(category[0])
        honest.append(vendor)
        if rng.random() < 0.6:
            b.insert('contracts', contract_id=b.ident('CTR'), vendor_rfc=vendor['rfc'], start_date=day(-rng.randrange(30, 700)),
                     value=round(limit * rng.uniform(2, 12), 2), scope_text=f'Contrato marco de {category[1].lower()}, vigencia anual, pago a 30 días.')
        for when in sorted(rng.sample(range(0, 170), rng.randrange(3, 8))):
            amount = background_amount()
            purchase(vendor, when, amount, po=amount >= 0.1 * limit or rng.random() < 0.7, reference=rng.random() < 0.8)
    for vendor in rng.sample(honest, 3):  # visible approval tier
        purchase(vendor, rng.randrange(0, 160), round(limit * rng.uniform(1.05, 2.5), 2))

    customers = []
    for _ in range(rng.randrange(10, 15)):
        known = rng.random() < 0.6
        customer = b.vendor('Cliente', registered=day(-rng.randrange(400, 3000))) if known else {'rfc': b.rfc(), 'bank_clabe': b.clabe()}
        customers.append(customer)
        for when in sorted(rng.sample(range(0, 175), rng.randrange(2, 6))):
            amount = round(limit * rng.uniform(0.1, 1.5), 2)
            metodo = 'PUE' if rng.random() < 0.75 else 'PPD'
            uuid = b.invoice(company, customer['rfc'], day(when), amount, 'Venta de producto terminado', sale=True, metodo=metodo, approver=rng.choice(accountants))
            collected = when + rng.randrange(0, 25)
            if collected <= end and (metodo == 'PUE' or rng.random() < 0.5):
                b.transfer(customer['bank_clabe'], company_clabe, amount, day(collected), f'Cobro {uuid}' if rng.random() < 0.8 else '')
    for _ in range(6):
        b.insert('efos_list', rfc=b.rfc(), legal_name=f'{rng.choice(WORDS)} Comercializadora SA de CV',
                 status=rng.choice(['definitivo', 'presunto']), publication_date=day(-rng.randrange(30, 900)))

    def scheme(kind, entities, amount, invoices, txns, difficulty):
        truth['schemes'].append({'scheme_id': f'S{len(truth["schemes"]) + 1}_{kind}', 'type': kind, 'entities': entities,
                                 'supporting_invoices': invoices, 'supporting_txns': [t for t in txns if t],
                                 'peso_amount': round(amount, 2), 'difficulty': difficulty})

    available = list(honest)
    rng.shuffle(available)
    selected = [] if clean else (scheme_types if scheme_types is not None else TYPES)
    entangled = available.pop() if {'kickback', 'threshold_splitting'} <= set(selected) else None

    if 'phantom_vendor' in selected:
        first = rng.randrange(20, 120)
        hard = rng.random() < 0.5
        if hard:
            shell = b.vendor('Consultoría', registered=day(first - rng.randrange(150, 400)))
            vendor = b.vendor('Consultoría', registered=day(first - rng.randrange(5, 90)), email=False, clabe=shell['bank_clabe'])
        else:
            vendor = b.vendor('Consultoría', registered=day(-rng.randrange(400, 2000)))
            b.insert('efos_list', rfc=vendor['rfc'], legal_name=vendor['legal_name'], status='definitivo', publication_date=day(first + rng.randrange(-60, 60)))
        orders = [purchase(vendor, first + i * rng.randrange(10, 25), round(limit * rng.uniform(0.3, 0.9), -2), po=False)
                  for i in range(rng.randrange(2, 5))]
        orders = [o for o in orders if o['txn']]
        scheme('phantom_vendor', ['RFC:' + vendor['rfc']], sum(b.conn.execute('SELECT total FROM invoices WHERE uuid=?', (o['invoice'],)).fetchone()[0] for o in orders),
               [o['invoice'] for o in orders], [o['txn'] for o in orders], 'hard' if hard else 'easy')

    kick_day = None
    if 'kickback' in selected:
        vendor = entangled or available.pop()
        employee = rng.choice(juniors)
        kick_day = rng.randrange(10, 60)
        amount = round(limit * rng.uniform(0.4, 0.95), -2)
        order = purchase(vendor, kick_day, amount, requester=employee['name'], approver=employee['name'])
        while not order['txn']:
            order = purchase(vendor, kick_day, amount, requester=employee['name'], approver=employee['name'])
        share = round(amount * rng.uniform(0.05, 0.15), 2)
        hops = []
        if rng.random() < 0.5:
            shell = b.clabe()
            hops.append(b.transfer(vendor['bank_clabe'], shell, share, day(order['paid_day'] + 1), 'Pago de servicios'))
            hops.append(b.transfer(shell, employee['bank_clabe'], share, day(order['paid_day'] + 3), 'Honorarios'))
        else:
            hops.append(b.transfer(vendor['bank_clabe'], employee['bank_clabe'], share, day(order['paid_day'] + 2), 'Comisión'))
        scheme('kickback', ['RFC:' + vendor['rfc'], employee['emp_id']], amount, [order['invoice']], [order['txn'], *hops],
               'hard' if len(hops) > 1 else 'medium')

    if 'round_tripping' in selected:
        outward = b.vendor('Consultoría', registered=day(-rng.randrange(400, 1500)))
        partner = b.vendor('Cliente', registered=day(-rng.randrange(400, 1500)))
        amount = round(limit * rng.uniform(0.6, 2.0), -2)
        when = rng.randrange(15, 100)
        order = purchase(outward, when, amount, pay=False)
        paid = when + 8
        pay = b.transfer(company_clabe, outward['bank_clabe'], amount, day(paid), f'Pago factura {order["invoice"]}')
        moved = round(amount * rng.uniform(0.97, 1.0), 2)
        hop = b.transfer(outward['bank_clabe'], partner['bank_clabe'], moved, day(paid + rng.randrange(1, 5)), 'Pago de servicios')
        back = round(moved * rng.uniform(0.95, 1.0), 2)
        back_day = paid + rng.randrange(8, 25)
        sale = b.invoice(company, partner['rfc'], day(back_day - 1), back, 'Venta de producto terminado', sale=True)
        receipt = b.transfer(partner['bank_clabe'], company_clabe, back, day(back_day), f'Cobro {sale}')
        scheme('round_tripping', ['RFC:' + outward['rfc'], 'RFC:' + partner['rfc']], amount, [order['invoice']], [pay, hop, receipt], 'hard')

    if 'threshold_splitting' in selected:
        vendor = entangled or available.pop()
        requester = rng.choice(requesters)
        approver = requester['name'] if rng.random() < 0.5 else rng.choice(juniors)['name']
        start = rng.randrange(100, 150) if kick_day is not None and entangled is vendor else rng.randrange(20, 150)
        description = 'Refacciones para línea de producción'
        orders = [purchase(vendor, start + rng.randrange(0, 6), round(limit * rng.uniform(0.6, 0.97), 2), requester=requester['name'],
                           approver=approver, description=description) for _ in range(rng.randrange(3, 6))]
        total = sum(b.conn.execute('SELECT amount FROM purchase_orders WHERE po_id=?', (o['po'],)).fetchone()[0] for o in orders)
        scheme('threshold_splitting', ['RFC:' + vendor['rfc'], requester['emp_id']], total, [o['invoice'] for o in orders],
               [o['txn'] for o in orders], 'medium' if entangled is vendor else 'easy')

    if 'revenue_inflation' in selected:
        if rng.random() < 0.5:
            customer = b.vendor('Cliente', registered=day(-rng.randrange(400, 1500)))
            amount = round(limit * rng.uniform(0.5, 2.0), 2)
            uuid = b.invoice(company, customer['rfc'], day(rng.randrange(30, 170)), amount, 'Venta de producto terminado', sale=True, status='cancelado')
            scheme('revenue_inflation', ['RFC:' + company, 'RFC:' + customer['rfc']], amount, [uuid], [], 'medium')
        else:
            first = rng.randrange(140, 160)
            customer = b.vendor('Cliente', registered=day(first - rng.randrange(10, 60)))
            uuids = [b.invoice(company, customer['rfc'], day(first + i * rng.randrange(2, 8)), round(limit * rng.uniform(0.3, 1.2), 2),
                               'Venta de producto terminado', sale=True) for i in range(rng.randrange(2, 4))]
            amount = sum(b.conn.execute('SELECT total FROM invoices WHERE uuid=?', (u,)).fetchone()[0] for u in uuids)
            scheme('revenue_inflation', ['RFC:' + company, 'RFC:' + customer['rfc']], amount, uuids, [], 'hard')

    def decoy(entity, signal, why, invoices=()):
        truth['decoys'].append({'entity': entity, 'signal': signal, 'why_innocent': why, 'invoices': list(invoices)})

    for n in range(10):
        kind, variant = TYPES[n % 5], 'A' if n < 5 else 'B'
        if kind == 'phantom_vendor':
            if variant == 'A':
                vendor = b.vendor('Mantenimiento')
                b.insert('efos_list', rfc=vendor['rfc'], legal_name=vendor['legal_name'], status='presunto', publication_date=day(rng.randrange(0, 120)))
                why = 'Only a presumed (presunto) SAT listing; purchase orders and a contract document the purchases.'
            else:
                first = rng.randrange(20, 100)
                vendor = b.vendor('Tecnología', registered=day(first - rng.randrange(5, 40)), email=False)
                why = 'A new supplier with thin master data, but every purchase has a purchase order and a signed contract.'
            b.insert('contracts', contract_id=b.ident('CTR'), vendor_rfc=vendor['rfc'], start_date=day(0), value=round(limit * 5, 2),
                     scope_text='Contrato de prestación de servicios con entregables mensuales.')
            orders = [purchase(vendor, rng.randrange(20, 150), round(limit * rng.uniform(0.2, 0.8), 2)) for _ in range(rng.randrange(2, 4))]
            decoy('RFC:' + vendor['rfc'], 'phantom_vendor', why, [o['invoice'] for o in orders])
        elif kind == 'kickback':
            vendor = b.vendor('Logística')
            employee = rng.choice(requesters)
            order = purchase(vendor, rng.randrange(20, 120), round(limit * rng.uniform(0.3, 0.9), 2))
            while not order['txn']:
                order = purchase(vendor, rng.randrange(20, 120), round(limit * rng.uniform(0.3, 0.9), 2))
            if variant == 'A':
                other = b.clabe(bank=employee['bank_clabe'][:3])
                b.transfer(vendor['bank_clabe'], other, round(rng.uniform(2_000, 9_000), 2), day(order['paid_day'] + 2), 'Pago a subcontratista')
                why = "The supplier paid an account at the same bank as an employee's, but the 18-digit CLABE is a different account."
            else:
                b.transfer(vendor['bank_clabe'], employee['bank_clabe'], round(rng.uniform(1_500, 6_000), 2), day(order['paid_day'] + 3),
                           'Reembolso de viáticos visita a planta del proveedor')
                why = 'The transfer to the employee reimburses documented travel expenses for a supplier site visit.'
            decoy('RFC:' + vendor['rfc'], 'kickback', why, [order['invoice']])
        elif kind == 'round_tripping':
            vendor = b.vendor('Materiales')
            when = rng.randrange(20, 120)
            order = purchase(vendor, when, round(limit * rng.uniform(0.4, 1.5), 2), pay=False)
            amount = b.conn.execute('SELECT total FROM invoices WHERE uuid=?', (order['invoice'],)).fetchone()[0]
            b.transfer(company_clabe, vendor['bank_clabe'], amount, day(when + 10), f'Pago factura {order["invoice"]}')
            if variant == 'A':
                b.transfer(company_clabe, vendor['bank_clabe'], amount, day(when + 11), f'Pago factura {order["invoice"]}')
                b.transfer(vendor['bank_clabe'], company_clabe, amount, day(when + 20), f'Devolución por pago duplicado {order["invoice"]}')
                why = 'The supplier returned a duplicated payment; the return references the duplicate and equals it exactly.'
            else:
                partial = round(amount * rng.uniform(0.3, 0.5), 2)
                sale = b.invoice(company, vendor['rfc'], day(when + 15), partial, 'Venta de producto terminado', sale=True)
                b.transfer(vendor['bank_clabe'], company_clabe, partial, day(when + 18), f'Cobro {sale}')
                why = 'The supplier is also a genuine customer; it paid a separate, smaller sales invoice.'
            decoy('RFC:' + vendor['rfc'], 'round_tripping', why, [order['invoice']])
        elif kind == 'threshold_splitting':
            vendor = b.vendor('Mantenimiento')
            requester = rng.choice(requesters)
            if variant == 'A':
                orders = [purchase(vendor, 5 + 32 * i, round(limit * rng.uniform(0.75, 0.95), 2), requester=requester['name'],
                                   description='Mantenimiento preventivo mensual') for i in range(5)]
                why = 'Monthly recurring maintenance orders a month apart, not one purchase split within days.'
            else:
                start = rng.randrange(20, 150)
                senior = rng.choice(seniors)['name']
                orders = [purchase(vendor, start + rng.randrange(0, 5), round(limit * rng.uniform(0.6, 0.9), 2), requester=requester['name'],
                                   approver=senior, description='Ampliación de almacén') for _ in range(3)]
                why = 'Orders near the limit in one week, but a director with authority over the total approved every one.'
            decoy('RFC:' + vendor['rfc'], 'threshold_splitting', why, [o['invoice'] for o in orders])
        else:
            customer = b.vendor('Cliente')
            if variant == 'A':
                amount = round(limit * rng.uniform(0.3, 1.2), 2)
                when = rng.randrange(20, 160)
                uuid = b.invoice(company, customer['rfc'], day(when), amount, 'Venta de producto terminado', sale=True, status='cancelado')
                b.ledger(day(when + 3), '4000', 'Ingresos', amount, 0, 'Reversión por cancelación', uuid, rng.choice(accountants))
                b.ledger(day(when + 3), '1100', 'Clientes', 0, amount, 'Reversión por cancelación', uuid, rng.choice(accountants))
                why = 'The cancelled invoice was fully reversed out of revenue.'
                invoices = [uuid]
            else:
                paid = b.invoice(company, customer['rfc'], day(rng.randrange(10, 60)), round(limit * 0.5, 2), 'Venta de producto terminado', sale=True)
                b.transfer(customer['bank_clabe'], company_clabe, round(limit * 0.5, 2), day(70), f'Cobro {paid}')
                invoices = [b.invoice(company, customer['rfc'], day(rng.randrange(140, 175)), round(limit * rng.uniform(0.4, 1.0), 2),
                                      'Venta de producto terminado', sale=True, metodo='PPD') for _ in range(2)]
                why = 'Uncollected invoices are PPD (deferred payment) to an established customer who has paid before.'
            decoy('RFC:' + customer['rfc'], 'revenue_inflation', why, invoices)
    b.serialize(path)
    return truth


def generate(seed, path, *, clean=False, scheme_types=None):
    """Typed-contract style (documentary predicates)."""
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
            entities = ['RFC:' + COMPANY, 'RFC:' + v[0]]
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


def export_csv_zip(db_path, zip_path):
    """Write the official estate_csv.zip form of a SQLite estate (UTF-8, header row, CLABEs as text)."""
    conn = sqlite3.connect(db_path)
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for table in TABLE_ORDER:
            cursor = conn.execute(f'SELECT * FROM {table}')
            columns = [c[0] for c in cursor.description]
            text = io.StringIO(newline='')
            writer = csv.writer(text, lineterminator='\n')
            writer.writerow(columns)
            for row in cursor:
                writer.writerow(['' if v is None else f'{v:.2f}' if c in MONEY else v for c, v in zip(columns, row)])
            archive.writestr(zipfile.ZipInfo(f'{table}.csv', (2026, 1, 1, 0, 0, 0)), text.getvalue().encode('utf-8'))
    conn.close()
    Path(zip_path).write_bytes(output.getvalue())


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--seed', type=int, required=True)
    parser.add_argument('--estate', type=Path, required=True)
    parser.add_argument('--answer-key', type=Path, required=True)
    parser.add_argument('--style', choices=['records', 'typed'], default='records')
    parser.add_argument('--csv-zip', type=Path, help='Also write the estate_csv.zip form')
    parser.add_argument('--clean', action='store_true')
    args = parser.parse_args()
    truth = (generate_records if args.style == 'records' else generate)(args.seed, args.estate, clean=args.clean)
    if args.csv_zip:
        export_csv_zip(args.estate, args.csv_zip)
    args.answer_key.parent.mkdir(parents=True, exist_ok=True)
    args.answer_key.write_text(json.dumps(truth, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Fictional {args.style} estate written to {args.estate}; company RFC {truth["company_rfc"]}. Answer key remains evaluator-only.')
