"""Present eight-table estates in the shared audit workspace, without changing judge contracts."""
import hashlib

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Literal

from . import api
from .estate import MONEY_FIELDS, DATE_FIELDS, IDS, AMOUNTS, cents
from .report import masked, LIMITATIONS, exposure

router = APIRouter(prefix='/api/estates/{identity}/workspace')


def reference(estate, table, rid):
    return 'E-' + hashlib.sha256(f'{estate.identity}:{table}:{rid}'.encode()).hexdigest()[:24]


def references(estate):
    return {f'{t}:{rid}': reference(estate, t, rid) for t, rows in estate.rows.items() for rid in rows}


def view(item):
    estate, case = item['estate'], item['case']
    result = dict(status=item['status'], mode=item.get('workspace_mode', 'offline'), leads=[], findings=[],
                  timeline=[], totals={}, limitations=LIMITATIONS, elapsed_seconds=0, model_calls=0,
                  total_definition='Documented exposure; findings can overlap. Bank hops and employee receipts are not added as additional loss.')
    if not case:
        result['completion_reason'] = ('Investigation failed before a case was available.' if item['status'] == 'failed'
                                       else 'Local evidence review is in progress; results appear when the bounded review finishes.')
        return result
    refs = references(estate)
    for finding in case['findings']:
        evidence = [refs[f"{ex['source_table']}:{ex['record_id']}"] for ex in finding['exhibits']]
        components = {}
        for ex in finding['exhibits']:
            table = ex['source_table']
            if table in AMOUNTS:
                value = estate.row(table, ex['record_id'])[AMOUNTS[table]]
                if value is not None:
                    components.setdefault(table, []).append(cents(value))
        calculation = '; '.join(f'{table}: ' + ' + '.join(map(str, values)) + f' = {sum(values)} centavos'
                                for table, values in components.items())
        result['findings'].append(dict(id=finding['lead_id'], title=finding['scheme_type'].replace('_', ' ').title(),
            rule=finding['rule_broken'], claim=finding['narrative'], confidence=finding['confidence'],
            supplier_name=', '.join(finding['entities']), invoice_id='', currency='MXN',
            amount_centavos=cents(finding['peso_amount']), amount_type='documented_exposure',
            calculation={'calculation': f"{finding['amount_definition']} Cited table sums (separate, not additive): {calculation}. Validated claim: {cents(finding['peso_amount'])} centavos; source reconciliation tolerance is 2%."},
            alternatives=[f"{c['argument']} — {c['check']}" for c in finding.get('challenges', [])], evidence=evidence))
        result['leads'].append(dict(id=finding['lead_id'], state='substantiated', reason=finding['narrative'],
                                    hypothesis=finding['scheme_type'], evidence=evidence))
    for lead in case['leads_not_pursued']:
        result['leads'].append(dict(id=lead['lead_id'], state=lead['state'], reason=lead['reason'],
                                    hypothesis=lead['signal'], evidence=[refs[r] for r in lead['evidence_examined']]))
    for entry in case['investigation_log']:
        evidence = [refs[r] for r in entry.get('evidence', []) if r in refs]
        result['timeline'].append(dict(step=len(result['timeline'])+1, lead_id=entry.get('lead_id', ''),
            tool='Evidence review', result=dict(reason=entry.get('alternative_review', entry.get('hypothesis', '')),
                checks=entry.get('tools', []), evidence=evidence)))
        edges, bank_refs = [], []
        for ref in entry.get('evidence', []):
            table, _, rid = ref.partition(':')
            if table == 'bank_txns' and rid in estate.rows[table]:
                row = estate.row(table, rid)
                edges.append(dict(id=refs[ref], source_account=row['from_clabe'], destination_account=row['to_clabe'],
                                  amount=cents(row['amount']), currency='MXN', timestamp=row['date']))
                bank_refs.append(refs[ref])
        if edges:
            result['timeline'].append(dict(step=len(result['timeline'])+1, lead_id=entry.get('lead_id', ''),
                tool='trace_funds', result=dict(edges=edges, evidence=bank_refs)))
    for entry in case.get('ai_events', []):
        result['timeline'].append(dict(step=len(result['timeline'])+1, lead_id=entry['lead_id'],
            tool=entry['tool'], result=dict(reason=entry['result'],
                evidence=[refs[r] for r in entry.get('evidence', []) if r in refs])))
    result.update(mode=case['run_metadata']['mode'], elapsed_seconds=case['run_metadata']['wall_clock_seconds'],
                  model_calls=case['run_metadata']['llm_calls'], totals={'MXN': exposure(case)},
                  limitations=LIMITATIONS + case.get('warnings', []), discovery=case.get('limits'),
                  completion_reason=case.get('completion_reason') or ('Review complete.' if case['status'] == 'offline_complete' else case['status'].replace('_', ' ')))
    return masked(estate, result)


@router.get('/case')
def get_case(identity: str):
    return view(api.session(identity))


class Start(BaseModel):
    mode: Literal['offline', 'ai'] = 'offline'
    usd_mxn_rate: str = ''
    fx_source: str = ''
    zdr: bool | None = None


@router.post('/investigate')
def investigate(identity: str, body: Start):
    api.start(identity, body.mode, body.usd_mxn_rate, body.fx_source, zdr=body.zdr)
    api.session(identity)['workspace_mode'] = body.mode
    return get_case(identity)


@router.post('/cancel')
def cancel(identity: str):
    return api.cancel(identity)


@router.delete('')
def delete(identity: str):
    return api.delete(identity)


def record_view(estate, table, rid, reveal=False, normalized=True):
    row = estate.row(table, rid)
    # Hide all source prose and identity fields by default, including short IDs.
    return {key: (cents(value) if normalized and value is not None else value) if key in MONEY_FIELDS else
            value if reveal or key in DATE_FIELDS or value is None else
            'Record-' + hashlib.sha256(f'{estate.identity}:{value}'.encode()).hexdigest()[:12]
            for key, value in row.items()}


@router.get('/records/{table}')
def records(identity: str, table: str, offset: int = 0):
    estate = api.session(identity)['estate']
    if table not in estate.rows or offset < 0:
        raise HTTPException(404, 'Unknown table or invalid offset')
    return {'total': len(estate.rows[table]), 'rows': [
        {**record_view(estate, table, rid), 'id': reference(estate, table, rid), 'evidence_id': reference(estate, table, rid)}
        for rid in list(estate.rows[table])[offset:offset+100]]}


@router.get('/evidence')
def evidence(identity: str, ref: str, reveal: bool = False):
    estate = api.session(identity)['estate']
    for table, rows in estate.rows.items():
        for rid in rows:
            if reference(estate, table, rid) == ref:
                return dict(id=ref, file=table, csv_record=f'{IDS[table]}={rid}' if reveal else ref,
                            sha256=estate.identity, ingestion_version='official-sqlite-v1 (normalized estate SHA-256)',
                            original=estate.row(table, rid) if reveal else record_view(estate, table, rid, normalized=False),
                            normalized=record_view(estate, table, rid, reveal))
    raise HTTPException(404, 'Evidence reference does not exist in this dataset')


@router.post('/ask')
def ask(identity: str, body: api.Question):
    item = api.session(identity)
    result = api.ask(identity, body)
    refs = references(item['estate'])
    masked_refs = {masked(item['estate'], {'value': ref})['value']: token for ref, token in refs.items()}
    result['evidence'] = [masked_refs[r] for r in result['evidence'] if r in masked_refs]
    return {**result, 'mode': body.mode, 'case_status': item['status']}


@router.get('/export/{kind}')
def export(identity: str, kind: str, full: bool = False):
    return api.export(identity, kind, reveal=full)


@router.post('/voice/session')
def voice_session(identity: str):
    item = api.session(identity)
    if not item['case']:
        raise HTTPException(409, 'Run an investigation before starting voice.')
    try:
        from ..voice import signed_session, VoiceError
        return signed_session()
    except VoiceError as error:
        raise HTTPException(502, str(error)) from None


@router.post('/voice/ask')
def voice_ask(identity: str, body: api.Question):
    item = api.session(identity)
    if not item['case']:
        raise HTTPException(409, 'Run an investigation before starting voice.')
    try:
        return ask(identity, api.Question(question=body.question, mode='ai'))
    except HTTPException as error:
        if error.status_code == 502:
            return ask(identity, api.Question(question=body.question, mode='offline'))
        raise
