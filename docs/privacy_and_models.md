# Model boundary and local data handling

Policy versions: `projection-v1`, `openrouter-deny-zdr-2026-09-12`. Official provider documentation was checked on September 12, 2026; live credentials are not present in this checkout.

Local source bytes and original record values remain the evidence source. Deterministic tools join identities and calculate amounts locally. The controller projects only random session/lead aliases, a fixed lead type, available/completed action names, counts of evidence/gaps/observed edges/cycles, allowlisted integer amount summaries, and a boolean predicate result. The model cannot retrieve arbitrary original records, choose unknown aliases, execute commands, or write a finding. Up to twelve actions for distinct leads can share one response; each action is revalidated before use. The model does not receive user Q&A text or the raw audit timeline.

Shareable views use separate stable aliases for source identities and references. They preserve calculation numbers and schema keys and omit descriptions, notes, references, source URLs and questions. This is a minimized audit view, not an anonymity guarantee: dates, amounts and graph patterns remain locally visible. Explicit source reveal/full exports are intentionally unmasked and must be handled accordingly. No authentication, encryption-at-rest service, or production deployment is claimed.

## Nemotron and other free endpoints

### Conversational Q&A boundary

Ask the Auditor now uses a separate case-context projection. Unlike the scheduling controller described above, it sends masked questions and the last six successful exchanges, alongside masked findings, calculations, leads, money trails and recorded investigation checks. Source originals, normalized records, descriptions, notes, references, URLs and prior Q&A timeline entries are removed. Known dataset identities are aliased and common RFC/contact/account patterns in questions are redacted. This does not recognize arbitrary new confidential prose: questions must stay focused on the case and must not introduce sensitive information. Local reveal never expands model access. The same free-demo/private-upload routing policy applies. One bounded call is made without retries; oversized contexts and invalid citations fail explicitly. Answers are generated explanations, not newly validated findings. History is session-local, bounded to six exchanges and cleared on a new CSV investigation. Offline extraction remains an explicit option.

Default ID: `nvidia/nemotron-3-ultra-550b-a55b:free`. The [model page](https://openrouter.ai/nvidia/nemotron-3-ultra-550b-a55b:free) says that its free endpoint logs use for product improvement and must not receive personal/confidential data. It also states that `response_format` is unsupported. The client therefore avoids that parameter and validates JSON locally. The [reasoning controls](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens) support explicitly disabling reasoning; defaults are `enabled: false`, `exclude: true`, with a 2048-token response budget rather than the previous 250 tokens.

Only `POST /api/datasets/demo` sets the in-memory trusted synthetic flag, after generating fictional records itself. No CSV field, filename, supplier label, uploaded metadata, or request body can claim this flag. An uploaded dataset cannot use a free model even if it was downloaded from the app earlier. The fixed connection-check prompt contains no records and can use the free endpoint.

For uploaded data, [provider routing](https://openrouter.ai/docs/guides/routing/provider-selection) enforces `data_collection=deny`, `zdr=true`, `allow_fallbacks=false`, and `require_parameters=true`. There is no downgrade or paid-model substitution on error. Check OpenRouter account-level prompt/completion logging separately; the application does not administer account settings. Routing flags cannot independently prove how infrastructure handles data.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Missing server key | Place `.env` beside `openrouter_client.py`; add `OPENROUTER_API_KEY`. Never paste it into the browser or chat. |
| Unexpected model name | `/api/config` shows the effective ID. Environment variables override `.env`; use the complete model slug. |
| HTTP 400 | Exact model ID and supported parameters. |
| HTTP 401 | Invalid/expired API key. |
| HTTP 403 | Model eligibility or account privacy settings; do not weaken uploaded-data protections. |
| HTTP 404 | Invalid ID or no endpoint satisfying the privacy/parameter requirements. |
| HTTP 429 | Free/provider rate limit. Wait before retrying; automatic retries are disabled. |
| Token limit | Keep `OPENROUTER_REASONING=off`, or raise `OPENROUTER_MAX_TOKENS` within 512–8192. |
| Timeout | Per-call default 40 seconds, configurable 5–60; the case deadline still applies. |
| Invalid controller response | Model failed the action schema, used an unknown alias or unavailable action. Case stays incomplete. |

`Check model connection` sends a fixed diagnostic and displays sanitized success/failure. It does not guarantee full-investigation latency, JSON compliance, rate-limit availability, or private-data endpoint eligibility. Missing credentials prevented live authenticated testing during this implementation.

## Retention

### ElevenLabs voice demo

The separate voice integration only accepts app-generated fictional datasets. It obtains an authenticated ElevenLabs WebRTC token without sending case data. Microphone audio goes directly from the browser to ElevenLabs; only masked auditor answers and citations return through the client tool. Audio cannot be locally redacted before transcription, so do not speak real confidential details. The browser starts transmission only after Start voice and microphone permission. End voice/navigation closes the connection; a pending connection is closed when SDK startup resolves. Setup requests recording off, one-day retention, and transcript/audio deletion, but does not establish zero retention or change workspace-wide privacy settings. The voice agent may paraphrase the grounded answer; its speech is not an evidence-gated finding. Uploaded data remains unavailable to voice pending a separate routing/privacy implementation. See README for setup and live-verification limits.

### Tiger Data archive

When `TIGER_DATABASE_URL` is set, each completed, cancelled or incomplete CSV investigation and each official estate run is written to the `analyses` table of that PostgreSQL service. Only the masked view is stored: the same projection the API returns by default (`Presentation.apply` for CSV, `masked()` for official estates), plus index columns derived from it. Original record values, uploaded files, replay bundles, AI Q&A history and local reveals are never written. Saving happens after the run ends and cannot change its result; failures are shown as `last_error` on `GET /api/analyses`. With the variable unset the app never connects.

This is still data leaving the machine. Masked views keep dates, amounts, graph shapes and the dataset SHA-256. CSV aliases are random per session and cannot be reversed. Official estate aliases are a truncated SHA-256 of the estate hash plus the value, and the estate hash is stored too, so someone with database access and a list of candidate RFCs, CLABEs or names could confirm guesses. Use a service with restricted credentials and delete saved analyses you do not need (`DELETE /api/analyses/{id}` or the Saved analyses view). Deleting a local dataset session does not delete its saved analysis.

Sessions and aliases live in process memory. Deletion cancels active work and removes the session after any in-flight request finishes. Restarting also loses sessions. Exported files and optional CLI SQLite archives persist independently; deletion in the app cannot retract earlier exports or provider requests. Credentials and provider response bodies are excluded from app errors. Run only on loopback.
## Optional Solana Devnet commitment

Case integrity sends only `FA:v1:<SHA-256 commitment>` to the fixed Solana Devnet RPC, together with the public signing wallet and standard transaction metadata. A private random nonce salts the manifest; the report, source fingerprint, nonce, identifiers and accounting values are not sent. The public wallet and transaction timing remain observable. Downloaded proof bundles contain the masked report, source fingerprint and nonce and can be correlated with the transaction; handle them as sensitive review artifacts. The backend key stays in ignored `tmp/solana-devnet-keypair.json`. Session deletion removes the in-memory receipt but cannot remove an already submitted commitment. Devnet may reset. See `docs/solana_integrity.md` for verification and retention limits. This feature does not transmit records to a model or change external-inference eligibility.
