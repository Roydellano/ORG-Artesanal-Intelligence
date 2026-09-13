"""Optional integrity sidecars; never modify official submissions or case status."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import threading
from typing import Literal

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from . import integrity as chain

router = APIRouter(prefix='/api/integrity', tags=['Devnet integrity'])
pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='devnet-integrity')
guard = threading.RLock()
Kind = Literal['datasets', 'estates']


def item_for(kind, identity):
    if kind == 'estates':
        from .official.api import session
        return session(identity)
    from .api import get_session
    return get_session(identity)


def snapshot(kind, identity):
    item = item_for(kind, identity)
    if kind == 'estates':
        from .official.report import masked, validate_publication
        case = item['case']
        if not case or case['status'] in ('running', 'queued'):
            raise HTTPException(409, 'Finish the investigation before sealing its report.')
        try:
            validate_publication(item['estate'], case)
        except ValueError:
            raise HTTPException(422, 'Case failed source evidence validation.') from None
        return item, item['estate'].identity, masked(item['estate'], case)
    from .api import case_file
    from .reporting import export_case
    case = case_file(identity, full=True)
    if case['status'] in ('running', 'queued'):
        raise HTTPException(409, 'Finish the investigation before sealing its report.')
    return item, item['data'].identity, export_case(item['data'], case, presentation=item['presentation'])


@router.get('/config')
def config():
    try:
        signer = str(chain.wallet().pubkey())
    except chain.IntegrityError:
        signer = None
    return {'network': 'devnet', 'signer': signer, 'configured': bool(signer)}


@router.post('/verify')
async def verify_upload(file: UploadFile):
    try:
        content = await file.read(20_000_001)
        if len(content) > 20_000_000:
            raise HTTPException(413, 'Integrity bundle limit is 20 MB.')
        proof = json.loads(content)
        return await run_in_threadpool(chain.verify, proof, str(chain.wallet().pubkey()))
    except (ValueError, TypeError, RecursionError):
        raise HTTPException(422, 'Bundle invalid or Devnet verification unavailable. Verify wallet configuration and connectivity.') from None
    finally:
        await file.close()


@router.get('/{kind}/{identity}')
def status(kind: Kind, identity: str):
    with guard:
        return public_state(item_for(kind, identity).get('integrity', {'status': 'not_anchored'}))


def public_state(state):
    result = {key: value for key, value in state.items() if key != 'proof'}
    if 'proof' in state:
        result['proof'] = {key: value for key, value in state['proof'].items() if key not in ('report', 'manifest')}
    return deepcopy(result)


@router.post('/{kind}/{identity}/anchor')
def anchor(kind: Kind, identity: str):
    try:
        chain.wallet()  # Fast local configuration check before queuing work.
    except chain.IntegrityError as error:
        raise HTTPException(409, str(error)) from None
    item, source_hash, report = snapshot(kind, identity)
    with guard:
        old = item.get('integrity')
        if old and old['status'] != 'failed':
            return public_state(old)
        proof = chain.make_proof(kind, source_hash, report)
        state = {'status': 'anchoring', 'proof': proof}
        item['integrity'] = state

    def work():
        try:
            encoded = chain.prepare(proof)
            # Persist signature in the in-memory receipt BEFORE network submission.
            # An uncertain send must only be verified, never automatically re-signed.
            with guard:
                state['status'] = 'submitted'
            chain.submit(encoded)
            result = chain.verify(proof, str(chain.wallet().pubkey()))
            with guard:
                state.update(result)
        except Exception:
            with guard:
                state.update(status='unavailable' if proof.get('signature') else 'failed',
                             message='Devnet anchoring unavailable. Check faucet funding/connectivity; verify again if a signature exists.')
    pool.submit(work)
    return {'status': 'anchoring'}


@router.post('/{kind}/{identity}/verify')
def verify_current(kind: Kind, identity: str):
    item, source_hash, report = snapshot(kind, identity)
    with guard:
        state = item.get('integrity')
        if not state or not state['proof'].get('signature'):
            raise HTTPException(409, 'No submitted integrity proof is available yet.')
        proof = deepcopy(state['proof'])
    try:
        result = chain.verify(proof, str(chain.wallet().pubkey()))
    except chain.IntegrityError as error:
        raise HTTPException(502, str(error)) from None
    result['current_report_matches'] = chain.digest(report) == proof['manifest']['report_sha256'] and source_hash == proof['manifest']['source_sha256']
    with guard:
        state.update(result)
    return public_state(state)


@router.get('/{kind}/{identity}/bundle')
def download(kind: Kind, identity: str):
    with guard:
        state = item_for(kind, identity).get('integrity')
        if not state or not state['proof'].get('signature'):
            raise HTTPException(409, 'No submitted integrity proof is available yet.')
        content = chain.canonical(state['proof'])
    return Response(content, media_type='application/json', headers={'Content-Disposition': 'attachment; filename="case.integrity.json"'})
