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

Sessions and aliases live in process memory. Deletion cancels active work and removes the session after any in-flight request finishes. Restarting also loses sessions. Exported files and optional CLI SQLite archives persist independently; deletion in the app cannot retract earlier exports or provider requests. Credentials and provider response bodies are excluded from app errors. Run only on loopback.
