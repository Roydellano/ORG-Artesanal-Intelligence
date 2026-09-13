# Solana Devnet integrity

This optional layer commits a frozen masked report and the existing input identity together at sealing time. It does not timestamp ingestion separately, certify source authenticity, validate fraud by consensus, or replace deterministic evidence checks. Official publication validation runs before sealing; the judge submission and replay contracts are unchanged.

## Protocol v1

- Source identity is the existing CSV dataset identity (hash of the sorted file-hash mapping) or official estate identity (SHA-256 of the loaded SQLite bytes). Equivalent official CSV ZIPs are represented by their loaded SQLite estate. The commitment binds that identity, not the transport ZIP byte layout.
- Report is a deep copy of the masked JSON export, including investigative decisions and version metadata already present in the export. Report status is preserved, including incomplete/offline labels.
- Manifest contains `format`, `kind`, `source_sha256`, `report_sha256`, and a cryptographically random 32-byte hex `nonce`.
- Canonical JSON is UTF-8 with sorted keys, compact separators, `ensure_ascii=False`, and `allow_nan=False`. SHA-256 is lowercase hex. This is a versioned Python JSON encoding, not a claim of RFC 8785 compatibility. Preserve number types; changing `1` to `1.0` changes the digest.
- `report_sha256 = SHA256(canonical(report))`; `commitment = SHA256(canonical(manifest))`.
- The public memo is exactly `FA:v1:<commitment>`. No source hashes, nonce, amounts, filenames, RFCs, or report text are sent to RPC. The auditor public wallet, transaction timing, and commitment are public.
- The receipt bundle contains the manifest, frozen report, commitment, network, signer and signature. It contains no private signing key. Anyone with the bundle can correlate it to its transaction; handle masked report contents according to their sensitivity.

The single Memo instruction uses one backend signature and no custom program deployment or account creation. The endpoint is fixed to `https://api.devnet.solana.com`; its full known genesis hash is checked before preparing and verifying transactions. There is no Mainnet switch. `solders` signs locally; HTTP requests have 12-second timeouts, no application-level automatic resend, and two bounded RPC submission retries. No priority fee is requested.

## Verification and lifecycle

`GET /api/integrity/config` returns only the public signer/configuration state. For `kind=datasets` or `estates`, use:

- `POST /api/integrity/{kind}/{identity}/anchor` to freeze and queue a seal.
- `GET /api/integrity/{kind}/{identity}` to read status.
- `POST /api/integrity/{kind}/{identity}/verify` to verify the frozen bundle and separately compare the current report/source identity with it.
- `GET /api/integrity/{kind}/{identity}/bundle` to download the immutable proof sidecar.
- `POST /api/integrity/verify` with multipart `file` to verify a saved bundle, even after its dataset session expires. This checks report integrity and the committed source fingerprint; it does not receive/recompute the original source files.

Verification obtains a finalized transaction from Devnet, requires successful execution, the expected signed auditor public key, the expected Memo program/data, and the matching signature. The configured local wallet establishes trust independently of the uploaded receipt. Remote reviewers can call `integrity.verify(proof, trusted_public_key)` with an independently authenticated public key; they do not need the private key. Verification trusts the configured Solana RPC's finalized view; it is not a light-client consensus proof.

`verified` refers to the frozen bundle, not the latest report. `current_report_matches=false` means the current case changed after sealing (including later CSV Q&A timeline entries). `changed` means a bundle's report or commitment is inconsistent; `untrusted`/`invalid` reject signer/transaction mismatches. `unavailable` is inconclusive, including pending transactions, expired submissions, unavailable historical data or a Devnet reset. Recheck manually after finalization. Anchoring never alters findings or investigation completion status.

One seal is retained per session. Repeat anchor requests reuse it, including uncertain submissions. A signature is retained before sending, so a timeout cannot cause automatic fresh signing. A pre-submission failure can be retried. Create a new investigation session to seal a revised report; keep both proof bundles. Submission may still complete after a dataset is deleted; deleting local data cannot remove an on-chain commitment.

Receipts and snapshots are in session memory until downloaded. They are not added to Tiger Data, HTML, official judge JSON or replay archives. Save the sidecar yourself before restarting/deleting the session. Keep the original evidence privately for independent source comparison. Public transaction-history availability depends on the RPC and Devnet, which may reset. This is demo integrity, not permanent archival.

The prototype remains loopback-only. Authentication, durable job/receipt storage, key custody hardening, production RPC and long-term verification are future work.

## Validation

Run `.\.venv\Scripts\python.exe -m pytest tests/test_integrity.py -q` and `npm --prefix web run build`. Tests cover canonicalization, random nonces, altered amounts/manifests, signer mismatch, wrong memo/program/signature, failed and unfinalized transactions, network mismatch, signed wire payload privacy, repeated requests, uncertain submissions, download/upload verification and changed current reports. Provider calls are mocked. Live faucet funding and a finalized round-trip require network access and available Devnet faucet SOL.

### Live verification — September 13, 2026

A fictional CSV excess-payment case (development seed 123) was sealed through the application's anchor endpoint and verified through its uploaded-bundle endpoint against the live Devnet RPC. The transaction finalized at slot `497616695`; the original bundle returned `verified`, and a copy with a finding amount increased by one centavo returned `changed`. Actual fee: 5,000 lamports (0.000005 Devnet SOL). Wallet balance after the test: 9.999995 Devnet SOL. Local artifacts are `tmp/devnet-live-proof.json` and `tmp/devnet-live-result.json`; the live check did not restart or clear the running application's sessions.

[Finalized demo transaction](https://explorer.solana.com/tx/5CTP3UFAzWFfTJsbKSbxYUD484LQzrECRmjTQiHKd3MbdtZRMW1TaBpeSR1sSzvHgA7QfwnPeMBTuBLdtdJBqnsa?cluster=devnet). This validates the backend RPC round-trip and tamper check, not a browser rehearsal or long-term Devnet retention.

Sources: [Memo program](https://github.com/solana-program/memo), [transaction submission](https://solana.com/docs/rpc/http/sendtransaction), [fees](https://solana.com/docs/core/fees), [Devnet limitations](https://solana.com/docs/references/clusters).
