"""Private proof bundles with public, Devnet-only SHA-256 commitments.

Canonical encoding v1: Python JSON, sorted keys, compact separators, UTF-8,
ensure_ascii=False, allow_nan=False. Preserve numeric types when verifying.
"""
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import secrets

import httpx
from solders.hash import Hash
from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.message import MessageV0
from solders.pubkey import Pubkey
from solders.signature import Signature
from solders.transaction import VersionedTransaction

RPC_URL = 'https://api.devnet.solana.com'
GENESIS = 'EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG'
MEMO = 'MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr'
KEY_PATH = Path(__file__).resolve().parents[1] / 'tmp/solana-devnet-keypair.json'
FORMAT = 'forensic-auditor-integrity-v1'


class IntegrityError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def wallet():
    try:
        return Keypair.from_bytes(bytes(json.loads(KEY_PATH.read_text())))
    except Exception:
        raise IntegrityError('Devnet wallet unavailable. Run python -m tools.setup_solana.') from None


def rpc(method, params=None):
    try:
        response = httpx.post(RPC_URL, json={'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or []}, timeout=12)
        response.raise_for_status()
        body = response.json()
        if 'error' in body or 'result' not in body:
            raise ValueError()
        return body['result']
    except Exception:
        # Provider errors may echo request data. Never expose them.
        raise IntegrityError(f'Devnet {method} unavailable or rejected. Check connectivity, faucet balance, and retry verification.') from None


def check_network():
    if rpc('getGenesisHash') != GENESIS:
        raise IntegrityError('RPC is not the expected Solana Devnet. Operation blocked.')


def make_proof(kind, source_hash, report):
    report = deepcopy(report)
    manifest = {'format': FORMAT, 'kind': kind, 'source_sha256': source_hash,
                'report_sha256': digest(report), 'nonce': secrets.token_hex(32)}
    return {'manifest': manifest, 'report': report, 'commitment': digest(manifest), 'network': 'devnet'}


def memo_text(proof):
    return f'FA:v1:{proof["commitment"]}'


def prepare(proof):
    check_network()
    signer = wallet()
    if rpc('getBalance', [str(signer.pubkey()), {'commitment': 'confirmed'}])['value'] < 5000:
        raise IntegrityError('Devnet wallet needs faucet SOL. Run python -m tools.setup_solana --airdrop.')
    blockhash = rpc('getLatestBlockhash', [{'commitment': 'confirmed'}])['value']['blockhash']
    instruction = Instruction(Pubkey.from_string(MEMO), memo_text(proof).encode(),
                              [AccountMeta(signer.pubkey(), True, False)])
    message = MessageV0.try_compile(signer.pubkey(), [instruction], [], Hash.from_string(blockhash))
    transaction = VersionedTransaction(message, [signer])
    proof.update(signer=str(signer.pubkey()), signature=str(transaction.signatures[0]))
    return base64.b64encode(bytes(transaction)).decode()


def submit(encoded):
    return rpc('sendTransaction', [encoded, {'encoding': 'base64', 'skipPreflight': False,
                                           'preflightCommitment': 'confirmed', 'maxRetries': 2}])


def verify(proof, trusted_signer):
    """Do not trust a signer, status, slot, or explorer URL supplied in a bundle."""
    try:
        manifest = proof['manifest']
        if (proof['network'] != 'devnet' or manifest['format'] != FORMAT
                or manifest['kind'] not in ('datasets', 'estates')
                or digest(proof['report']) != manifest['report_sha256']
                or digest(manifest) != proof['commitment']):
            return {'status': 'changed', 'message': 'Report or commitment does not match the sealed bundle.'}
        Pubkey.from_string(trusted_signer)
        Signature.from_string(proof['signature'])
        if proof['signer'] != trusted_signer:
            return {'status': 'untrusted', 'message': 'Bundle signer differs from the trusted auditor wallet.'}
    except (KeyError, TypeError, ValueError):
        raise IntegrityError('Invalid integrity bundle.') from None
    check_network()
    tx = rpc('getTransaction', [proof['signature'], {'encoding': 'jsonParsed', 'commitment': 'finalized', 'maxSupportedTransactionVersion': 0}])
    if tx is None:
        return {'status': 'unavailable', 'message': 'No finalized transaction found. It may be pending, expired, or lost in a Devnet reset.'}
    try:
        message = tx['transaction']['message']
        signed = any(k['pubkey'] == trusted_signer and k['signer'] for k in message['accountKeys'])
        matched = any(i.get('programId') == MEMO and i.get('parsed') == memo_text(proof) for i in message['instructions'])
        if (tx['meta']['err'] is not None or not signed or not matched
                or tx['transaction']['signatures'][0] != proof['signature']):
            return {'status': 'invalid', 'message': 'Transaction failed or its signer/memo does not match.'}
        return {'status': 'verified', 'message': 'Frozen report integrity verified on Solana Devnet.',
                'slot': tx['slot'], 'block_time': tx.get('blockTime'), 'fee_lamports': tx['meta']['fee'],
                'explorer_url': f'https://explorer.solana.com/tx/{proof["signature"]}?cluster=devnet'}
    except (KeyError, TypeError, IndexError):
        raise IntegrityError('Devnet returned an invalid transaction response.') from None
