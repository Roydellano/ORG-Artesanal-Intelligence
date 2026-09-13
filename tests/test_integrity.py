from copy import deepcopy
import base64
import json
import time

from fastapi.testclient import TestClient
import pytest
from solders.keypair import Keypair
from solders.hash import Hash
from solders.signature import Signature
from solders.transaction import VersionedTransaction

from forensic_auditor import integrity as chain
from forensic_auditor import integrity_api as api


@pytest.fixture
def wallet(monkeypatch):
    key = Keypair()
    monkeypatch.setattr(chain, 'wallet', lambda: key)
    return key


def proof_for(key):
    proof = chain.make_proof('datasets', 'a' * 64, {'amount_centavos': 12345, 'status': 'offline_complete'})
    proof.update(signer=str(key.pubkey()), signature=str(Signature.default()))
    return proof


def transaction_for(proof):
    return {'meta': {'err': None, 'fee': 5000}, 'slot': 123, 'blockTime': 456,
            'transaction': {'signatures': [proof['signature']], 'message': {
                'accountKeys': [{'pubkey': proof['signer'], 'signer': True}],
                'instructions': [{'programId': chain.MEMO, 'parsed': chain.memo_text(proof)}]}}}


def mock_network(monkeypatch, tx):
    monkeypatch.setattr(chain, 'rpc', lambda method, params=None: chain.GENESIS if method == 'getGenesisHash' else tx)


def test_verified_and_amount_tamper(monkeypatch, wallet):
    proof = proof_for(wallet)
    mock_network(monkeypatch, transaction_for(proof))
    assert chain.verify(proof, str(wallet.pubkey()))['status'] == 'verified'
    proof['report']['amount_centavos'] += 1
    assert chain.verify(proof, str(wallet.pubkey()))['status'] == 'changed'


@pytest.mark.parametrize('change', ['source', 'nonce', 'hash', 'network'])
def test_manifest_tampering(wallet, change):
    proof = proof_for(wallet)
    if change == 'source': proof['manifest']['source_sha256'] = 'b' * 64
    if change == 'nonce': proof['manifest']['nonce'] = 'b' * 64
    if change == 'hash': proof['commitment'] = 'b' * 64
    if change == 'network': proof['network'] = 'mainnet'
    assert chain.verify(proof, str(wallet.pubkey()))['status'] == 'changed'


@pytest.mark.parametrize('change', ['failed', 'memo', 'program', 'unsigned', 'signature'])
def test_rejects_wrong_transaction(monkeypatch, wallet, change):
    proof = proof_for(wallet)
    tx = transaction_for(proof)
    message = tx['transaction']['message']
    if change == 'failed': tx['meta']['err'] = {'InstructionError': [0, 'InvalidArgument']}
    if change == 'memo': message['instructions'][0]['parsed'] = 'FA:v1:wrong'
    if change == 'program': message['instructions'][0]['programId'] = str(wallet.pubkey())
    if change == 'unsigned': message['accountKeys'][0]['signer'] = False
    if change == 'signature': tx['transaction']['signatures'] = ['wrong']
    mock_network(monkeypatch, tx)
    assert chain.verify(proof, str(wallet.pubkey()))['status'] == 'invalid'


def test_resigned_forgery_and_pending(monkeypatch, wallet):
    proof = proof_for(wallet)
    assert chain.verify(proof, str(Keypair().pubkey()))['status'] == 'untrusted'
    mock_network(monkeypatch, None)
    assert chain.verify(proof, str(wallet.pubkey()))['status'] == 'unavailable'
    monkeypatch.setattr(chain, 'rpc', lambda *args: 'mainnet-genesis')
    with pytest.raises(chain.IntegrityError, match='Operation blocked'):
        chain.verify(proof, str(wallet.pubkey()))


def test_wire_contains_only_commitment(monkeypatch, wallet):
    proof = chain.make_proof('estates', 'a' * 64, {'private_canary': 'SECRET-RFC', 'amount': 123})
    calls = []
    def rpc(method, params=None):
        calls.append((method, params))
        return {'getGenesisHash': chain.GENESIS, 'getBalance': {'value': 1000000},
                'getLatestBlockhash': {'value': {'blockhash': str(Hash.default())}}}[method]
    monkeypatch.setattr(chain, 'rpc', rpc)
    encoded = chain.prepare(proof)
    tx = VersionedTransaction.from_bytes(base64.b64decode(encoded))
    assert tx.verify_with_results() == [True]
    assert bytes(tx.message.instructions[0].data) == chain.memo_text(proof).encode()
    assert b'SECRET-RFC' not in bytes(tx)
    assert proof['manifest']['nonce'].encode() not in bytes(tx)
    assert 'SECRET-RFC' not in json.dumps(calls)
    assert tx.message.header.num_required_signatures == 1


def test_encoding_is_stable_and_nonce_random():
    a = chain.make_proof('datasets', 'a' * 64, {'b': 2, 'a': 'ñ'})
    b = chain.make_proof('datasets', 'a' * 64, {'a': 'ñ', 'b': 2})
    assert a['manifest']['report_sha256'] == b['manifest']['report_sha256']
    assert a['commitment'] != b['commitment']
    with pytest.raises(ValueError): chain.digest({'amount': float('nan')})


def test_api_snapshot_download_verify_and_idempotency(monkeypatch, wallet):
    from forensic_auditor.api import app
    item = {}
    report = {'amount_centavos': 12345}
    monkeypatch.setattr(api, 'item_for', lambda *args: item)
    monkeypatch.setattr(api, 'snapshot', lambda *args: (item, 'a' * 64, deepcopy(report)))
    submitted = []
    def prepare(proof):
        proof.update(signer=str(wallet.pubkey()), signature=str(Signature.default()))
        return 'encoded'
    monkeypatch.setattr(chain, 'prepare', prepare)
    monkeypatch.setattr(chain, 'submit', lambda encoded: submitted.append(encoded))
    monkeypatch.setattr(chain, 'rpc', lambda method, params=None: chain.GENESIS if method == 'getGenesisHash' else transaction_for(item['integrity']['proof']))
    client = TestClient(app)
    path = '/api/integrity/datasets/test'
    assert client.post(path + '/anchor').status_code == 200
    for _ in range(100):
        if client.get(path).json()['status'] == 'verified': break
        time.sleep(.01)
    assert client.get(path).json()['status'] == 'verified'
    client.post(path + '/anchor')
    assert submitted == ['encoded']
    bundle = client.get(path + '/bundle').json()
    result = client.post('/api/integrity/verify', files={'file': ('proof.json', json.dumps(bundle))})
    assert result.json()['status'] == 'verified'
    report['amount_centavos'] += 1
    assert client.post(path + '/verify').json()['current_report_matches'] is False
    bundle['report']['amount_centavos'] += 1
    assert client.post('/api/integrity/verify', files={'file': ('proof.json', json.dumps(bundle))}).json()['status'] == 'changed'


def test_uncertain_send_keeps_receipt_without_resubmitting(monkeypatch, wallet):
    item = {}
    monkeypatch.setattr(api, 'item_for', lambda *args: item)
    monkeypatch.setattr(api, 'snapshot', lambda *args: (item, 'a' * 64, {}))
    def prepare(proof):
        proof.update(signer=str(wallet.pubkey()), signature=str(Signature.default()))
        return 'encoded'
    def fail(*args): raise chain.IntegrityError('timeout')
    monkeypatch.setattr(chain, 'prepare', prepare)
    monkeypatch.setattr(chain, 'submit', fail)
    api.anchor('datasets', 'test')
    for _ in range(100):
        if item['integrity']['status'] == 'unavailable': break
        time.sleep(.01)
    assert api.anchor('datasets', 'test')['status'] == 'unavailable'
    assert item['integrity']['proof']['signature']


def test_csv_snapshot_requires_finished_run():
    from forensic_auditor import api as csv
    from forensic_auditor.investigation import Investigation
    from forensic_auditor.synthetic_records import records
    from fastapi import HTTPException
    registered = csv.register(records(123, 'excess', False), synthetic=True)
    identity = registered['session_id']
    item = csv.get_session(identity)
    try:
        item['job'] = Investigation(item['data'], 'offline', 60, 180, synthetic=True)
        with pytest.raises(HTTPException): api.snapshot('datasets', identity)
        item['job'].run()
        _, source_hash, report = api.snapshot('datasets', identity)
        assert source_hash == item['data'].identity
        assert report['privacy_mode'] == 'masked shareable case'
        assert report['findings']
    finally:
        csv.sessions.pop(identity, None)


def test_official_snapshot_revalidates_source(tmp_path):
    from forensic_auditor.official import api as official
    from forensic_auditor.official.estate import load
    from forensic_auditor.official.audit import investigate
    from tools.official_generate import generate, COMPANY
    from fastapi import HTTPException
    path = tmp_path / 'estate.db'
    generate(101, path)
    estate = load(path.read_bytes())
    case = investigate(estate, 101, COMPANY)
    identity = official.register(estate, 101, COMPANY, case)['session_id']
    try:
        _, source_hash, report = api.snapshot('estates', identity)
        assert source_hash == estate.identity
        assert report['findings']
        case['estate_sha256'] = 'wrong'
        with pytest.raises(HTTPException) as error: api.snapshot('estates', identity)
        assert error.value.status_code == 422
    finally:
        official.sessions.pop(identity, None)
