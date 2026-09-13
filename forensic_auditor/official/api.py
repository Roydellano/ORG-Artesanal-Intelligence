"""Official estate endpoints isolated from generation and evaluation tooling."""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
import threading
from uuid import uuid4
from typing import Literal

from fastapi import APIRouter, HTTPException, UploadFile, Query
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from .estate import load_any, infer_company
from .audit import investigate
from .report import answer, bundle, canonical, masked, render, replay, validate_publication
from ..qa import explain
from .. import storage
from openrouter_client import OpenRouterError

router = APIRouter(prefix='/api/estates', tags=['Official student-materials'])
sessions = OrderedDict()
guard = threading.RLock()
pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='official-auditor')


def session(identity):
    with guard:
        if identity not in sessions:
            raise HTTPException(404, 'Estate session not found')
        return sessions[identity]


def register(estate, seed, company, case=None):
    if not company or len(company) > 100:
        raise HTTPException(422, 'Provide the audited company RFC')
    with guard:
        if len(sessions) >= 8:
            raise HTTPException(429, 'Eight estates are already open; delete one before uploading')
        sid = uuid4().hex
        sessions[sid] = {'estate': estate, 'seed': seed, 'company': company, 'case': case,
                         'cancel': threading.Event(), 'status': case['status'] if case else 'ready'}
    return {'session_id': sid, 'coverage': {t: len(r) for t, r in estate.rows.items()}, 'estate_sha256': estate.identity,
            'company_rfc': company, 'status': sessions[sid]['status']}


@router.post('/upload')
async def upload(file: UploadFile, seed: int = Query(ge=0), company_rfc: str = Query(default='', max_length=100)):
    try:
        content = await file.read(20_000_001)
        estate = load_any(content)
        return register(estate, seed, company_rfc.strip() or infer_company(estate))
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    finally:
        await file.close()


@router.post('/replay')
async def restore(file: UploadFile):
    try:
        content = await file.read(40_000_001)
        if len(content) > 40_000_000:
            raise ValueError('Replay limit is 40 MB')
        estate, case = replay(content)
        return register(estate, case['seed'], case['company_rfc'], case)
    except Exception as error:
        if isinstance(error, HTTPException):
            raise
        raise HTTPException(422, 'Replay archive failed structure or evidence validation') from None
    finally:
        await file.close()


@router.post('/{identity}/run')
def start(identity: str, mode: Literal['offline', 'ai'] = 'offline', usd_mxn_rate: str = '', fx_source: str = Query(default='', max_length=500)):
    item = session(identity)
    if mode == 'ai':
        from openrouter_client import settings
        from decimal import Decimal, InvalidOperation
        config = settings()
        if config['model'].endswith(':free') or not config['api_key']:
            raise HTTPException(422, 'Official uploaded estates need offline mode or a configured non-free model with no-collection/ZDR routing')
        try:
            rate = Decimal(usd_mxn_rate)
            if not rate.is_finite() or not 0 < rate < 1000 or not fx_source.strip():
                raise ValueError()
        except (InvalidOperation, ValueError):
            raise HTTPException(422, 'Provide a positive USD/MXN rate and its source to measure AI cost') from None
    with guard:
        if item['status'] == 'running':
            raise HTTPException(409, 'Investigation is already running')
        if item['case']:
            return {'status': item['status'], 'replayed': True}
        item['status'] = 'running'
        item['cancel'].clear()
    def work():
        try:
            if mode == 'ai':
                from .agent import run
                result = run(item['estate'], item['seed'], item['company'], cancelled=item['cancel'], usd_mxn_rate=usd_mxn_rate, fx_source=fx_source)
            else:
                result = investigate(item['estate'], item['seed'], item['company'], cancelled=item['cancel'])
            with guard:
                item['case'] = result
                item['status'] = result['status']
            storage.archive('official', masked(item['estate'], result))
        except Exception:
            with guard:
                item['status'] = 'failed'
    pool.submit(work)
    return {'status': 'running'}


@router.post('/{identity}/cancel')
def cancel(identity: str):
    session(identity)['cancel'].set()
    return {'status': 'cancellation_requested'}


@router.get('/{identity}/case')
def get_case(identity: str, reveal: bool = False):
    item = session(identity)
    with guard:
        if item['case'] is None:
            return {'status': item['status']}
        return item['case'] if reveal else masked(item['estate'], item['case'])


@router.get('/{identity}/export/{kind}')
def export(identity: str, kind: str, reveal: bool = False):
    item = session(identity)
    if not item['case']:
        raise HTTPException(409, 'No completed case is available')
    estate, case = item['estate'], item['case']
    validate_publication(estate, case)
    if kind == 'html':
        return HTMLResponse(render(estate, case, reveal=reveal))
    if kind == 'json':
        if reveal and case['run_metadata']['mxn_cost'] is None:
            raise HTTPException(409, 'Provider cost was unavailable. Save the incomplete replay/HTML; a compliant judge submission requires measured cost.')
        return Response(canonical(case if reveal else masked(estate, case)), media_type='application/json',
                        headers={'Content-Disposition': 'attachment; filename="submission.json"'})
    if kind == 'replay' and reveal:
        return Response(bundle(estate, case), media_type='application/zip', headers={'Content-Disposition': 'attachment; filename="case.replay.zip"'})
    raise HTTPException(422, 'Choose html, json, or explicit original replay export')


@router.get('/{identity}/evidence/{table}/{record_id:path}')
def evidence(identity: str, table: str, record_id: str, reveal: bool = False):
    item = session(identity)
    try:
        result = item['estate'].evidence(table, record_id)
    except KeyError:
        raise HTTPException(404, 'Source record not found') from None
    if not reveal:
        result['original'] = '[Original values hidden; reveal locally to inspect]'
    return result


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    mode: Literal['ai', 'offline'] = 'ai'


@router.post('/{identity}/ask')
def ask(identity: str, body: Question, reveal: bool = False):
    item = session(identity)
    if not item['case']:
        raise HTTPException(409, 'Run the investigation first')
    if body.mode == 'offline':
        case = item['case'] if reveal else masked(item['estate'], item['case'])
        return answer(case, body.question)
    estate = item['estate']
    def mask(value):
        return masked(estate, {'value': value})['value']
    refs = [f'{table}:{rid}' for table, rows in estate.rows.items() for rid in rows]
    try:
        result = explain(item['case'], body.question, refs, mask=mask,
                         history=item.get('qa_history', []))
    except OpenRouterError as error:
        raise HTTPException(502, str(error)) from None
    item['qa_history'] = (item.get('qa_history', []) + [result.pop('_history')])[-6:]
    return mask(result)


@router.delete('/{identity}')
def delete(identity: str):
    item = session(identity)
    item['cancel'].set()
    with guard:
        del sessions[identity]
    return {'deleted': True}
