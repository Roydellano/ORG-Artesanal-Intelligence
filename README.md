# The Forensic Auditor

**Student-materials support:** the Overview now includes the official eight-table SQLite estate workflow, all five scheme enums with narrow corroborated predicates, judge JSON, standalone diagram-rich HTML, masked/original evidence views, saved-case Q&A, and completed-run replay. See [official estate setup and limits](docs/official_estates.md). The existing ZIP/CSV workspace remains available. Original judge JSON must be exported with local identity reveal; masked aliases do not resolve against the original estate.

Quick official-format verification:

```powershell
.\.venv\Scripts\python.exe -m tools.official_generate --seed 101 --estate tmp\estate.db --answer-key tmp\evaluator-only\answer-key.json
.\.venv\Scripts\python.exe -m forensic_auditor.official run tmp\estate.db --seed 101 --company-rfc EMP920101AB1 --output tmp\judge-case
.\.venv\Scripts\python.exe specs\student-materials\forensic-auditor\validate_format.py --submission tmp\judge-case.json --estate tmp\estate.db
.\.venv\Scripts\python.exe -m tools.official_evaluate --output tmp\official-evaluation
```

The official SQLite path requires Python 3.11+ with SQLite deserialization support. Five supported scheme names do not imply universal detection: unknown accounting semantics, missing ownership and unrecognized contract prose remain explicit gaps. Live AI scheduling and provider cost capture are implemented with masked context and safe failure, but authenticated live latency/billing and the timed human demo still need verification.

HackMTY 2026 Infosys forensic investigation project. See [AGENTS.md](AGENTS.md) for project rules and [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for the roadmap.

Working local MVP: **bare React + TypeScript + Vite** frontend and **FastAPI + Pydantic + NetworkX** backend. Includes ZIP/CSV ingestion, exact reconciliation, four versioned accounting rules, independent bank-flow discovery, fictional multi-scheme injections, source provenance, audit timeline, masked API views/exports, local source reveal, and grounded case Q&A.

Offline review works without a model and is clearly labeled separately from AI investigation. OpenRouter directs the bounded tool loop using your configured model; the default is Nemotron 3 Ultra free for app-generated fictional demos.

## Run locally (PowerShell, Python 3.10+, Node.js 20.19+)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm --prefix web ci
npm --prefix web run build
.\.venv\Scripts\python.exe -m uvicorn forensic_auditor.api:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000**, load the demo, keep Offline evidence review selected, and start an investigation. All five views use the live API; findings are not hard-coded in React. Build before starting the API so static assets are mounted.

For React development, keep the API running and start Vite in a second terminal:

```powershell
npm --prefix web run dev
```

Open the printed Vite URL (normally http://127.0.0.1:5173). Vite proxies `/api` to port 8000. API docs: http://127.0.0.1:8000/docs.

On Windows, after installing dependencies, double-click `restart-servers.bat` to restart the API (8000) and Vite (5173) in the background. Open http://127.0.0.1:5173 for the current frontend; logs are in `tmp/servers/`. The launcher uses `scripts/restart-servers.ps1`, checks readiness, and refuses to stop a port owner it cannot identify as this project's server. Restarting the API clears in-memory datasets and investigations. This development shortcut does not rebuild the static frontend served on port 8000.

## AI configuration

### Real-time voice for the hackathon

1. Add `ELEVENLABS_API_KEY` to your local `.env` (never browser code). Keep your existing `OPENROUTER_API_KEY`: the auditor still uses it for grounded answers. Optionally set `ELEVENLABS_VOICE_ID` to a voice you can access.
2. Create the private voice agent once:

   ```powershell
   .\.venv\Scripts\python.exe -m tools.setup_voice
   ```

   This creates an `ask_auditor` client tool and an ElevenLabs agent, then saves their IDs in `.env` without replacing existing keys. The voice agent uses Gemini 2.5 Flash for conversation and delegates case questions to the configured OpenRouter auditor. Existing configured agents are left unchanged. The ElevenLabs key needs permission to create tools/agents and obtain conversation tokens. Review your account's available credits before the demo; voice usage is separate from OpenRouter usage.
3. Build the frontend and restart the backend after installing this update. Load an **app-generated demo**, run an investigation, open **Ask the auditor**, and click **Start voice**. Allow microphone access. Ask in Spanish or English, interrupt naturally, or click **End voice**. Case answers and their citations appear in the existing chat; live speech transcripts appear in the voice panel.

The browser uses ElevenLabs' authenticated WebRTC connection for microphone input, turn detection, interruptions and audio playback; no public tunnel is needed. Conversation tokens are ephemeral bearer credentials and must not be shared. The agent calls the browser's bounded `ask_auditor` tool, which invokes the local API and returns only the masked answer and citations. It receives no estate files or source-record dump. Sessions end after three minutes and the UI permits eight case questions. Leaving the auditor view ends voice. Auditing still waits for OpenRouter's complete response, so real-time audio does not guarantee instant case answers. Spoken summaries can differ from the cited answer and never change findings.

Voice currently rejects uploaded datasets, including downloaded demos that are re-uploaded. Microphone audio is transmitted directly to ElevenLabs and cannot be masked locally; keep speech limited to fictional case questions. Agent setup disables voice recording and requests one-day transcript retention with deletion; it does not establish ZDR or administer account-wide logging. Existing OpenRouter privacy controls do not automatically apply to ElevenLabs. See [ElevenLabs client tools](https://elevenlabs.io/docs/eleven-agents/customization/tools/client-tools) and [WebRTC token authentication](https://elevenlabs.io/docs/api-reference/conversations/get-webrtc-token).

The voice panel shows a live microphone input meter and allows muting and switching microphones during a call. If speech does not move the meter, choose the correct input and check its hardware mute. Recognized user speech appears in the transcript. Voice uses WebRTC with LiveKit pinned to 2.16.1 for ElevenLabs compatibility. Restart the backend and refresh the frontend together after this transport update; existing ElevenLabs agents do not need recreation.

Validation uses mocked provider calls. Live microphone quality, interruptions, account provisioning, credit usage and end-to-end latency need a configured ElevenLabs key and a human rehearsal.

Auditor answers render Markdown in both case views, including emphasis, nested lists, tables, quotes and code blocks. Raw HTML and automatic remote images are disabled; evidence citation controls remain separate.

**Ask the Auditor** defaults to conversational AI in both case views, independently of investigation mode. It receives masked findings, calculations, money trails, lead dispositions and recorded checks, plus the last six successful exchanges. Known dataset identities and common contact/RFC/account patterns in questions are masked; do not add new confidential details. Citations must resolve to evidence in the current case. Explanations do not modify validated findings; citation existence does not guarantee prose correctness. Provider failures are displayed explicitly. Select **Offline case extraction** for network-free answers. Uploaded records still require a non-free model with no-collection/ZDR routing. Oversized context fails explicitly. The narrower controller projection described below applies to investigation scheduling, not conversational Q&A.

Create `.env` from `.env.example` if it does not already exist. Keep an existing `.env`; do not overwrite your key. Fill it in:

```dotenv
OPENROUTER_API_KEY=your_openrouter_key
OPENROUTER_MODEL=nvidia/nemotron-3-ultra-550b-a55b:free
OPENROUTER_MAX_TOKENS=2048
OPENROUTER_TIMEOUT_SECONDS=40
OPENROUTER_REASONING=off
```

Use the exact provider model ID including `:free`. System environment variables override `.env`. The Overview page shows the effective model and whether a server key exists; it never returns the key. Configuration is read on new requests. Restart an old running backend after updating the code, and rebuild the frontend. `/api/config` and the **Check model connection** button provide sanitized diagnostics.

Only typed pseudonymous summaries cross the model boundary: random session/lead aliases, lead type, permitted/completed actions, evidence/missing counts, and a verified-predicate boolean. Raw records, names, RFCs, accounts, descriptions, references, URLs, notes and user questions are excluded. Amount calculations and identity joins remain local. Responses must be locally valid JSON actions; one fenced JSON document is accepted, arbitrary prose is not. Up to twelve independent lead actions can be returned per call. Defaults: 60 tool steps, 180 seconds, 40 seconds per model request, 2048 output tokens, zero automatic retries. Cancellation stops before the next action and interrupts discovery; a remote request can finish its configured timeout.

The old 250-token response limit could truncate a reasoning model before its JSON action. Reasoning is now disabled by default and excluded from returned output. No `response_format` is forced because this free endpoint does not support it. HTTP 401/403/404/429, token truncation, invalid responses and timeouts have controlled, actionable messages. No provider error body or private reasoning is displayed. Model availability and rate limits still depend on OpenRouter/NVIDIA.

**Free-model privacy:** the [Nemotron free endpoint notice](https://openrouter.ai/nvidia/nemotron-3-ultra-550b-a55b:free) prohibits confidential/personal data and describes usage logging for product improvement. Free model IDs are therefore accepted only for datasets generated inside the app. Downloading and re-uploading such a ZIP does not grant it trusted synthetic status. Uploaded datasets use offline mode or a non-free model routed with `data_collection: deny`, `zdr: true`, `allow_fallbacks: false`, and `require_parameters: true`. A model with no eligible endpoint fails; protections are never relaxed automatically. These controls were checked against [OpenRouter provider routing](https://openrouter.ai/docs/guides/routing/provider-selection) on September 12, 2026. They are provider routing commitments, not a claim of independent auditing of provider infrastructure. Check account-level prompt logging settings separately; pseudonymous investigation patterns can still be sensitive.

The per-investigation cache includes dataset identity, model ID, prompt/privacy version and projected context. It never crosses dataset sessions. Provider-internal model revisions are not observable/pinned. Deleting a dataset cancels active work and releases its data, aliases and caches after in-flight work ends. This does not delete previously downloaded exports or optional SQLite archives.

## Check the API connection

After adding your key, run:

```powershell
.\.venv\Scripts\python.exe openrouter_client.py
```

This sends a small prompt to OpenRouter using the selected model and consumes API credit. It does not send project files or accounting records. The client has a 60-second network timeout and makes no automatic retries. Missing configuration, HTTP errors, and incomplete responses produce explicit errors.

The controller calls `chat` with a shorter timeout and locally validates JSON action responses using Pydantic. The standalone connection check retains its 60-second timeout.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m forensic_auditor.evaluate --output tmp/holdout-evaluation.json
.\.venv\Scripts\python.exe -m forensic_auditor.evaluate --extended --output tmp/extended-evaluation.json
npm --prefix web test
npm --prefix web run build
```

Tests mock transport and never use your real key. They cover exact amounts, clean controls, split/consolidated payments, refunds/credits, ownership gaps, missing/forged citations, currency separation, bounded traces, SAT history, uploaded instruction injection, malformed responses, cancellation, dataset isolation and fresh upload-to-export API flow. Existing client tests also run with `python -m unittest discover -s tests -v`.

## Input and live demo

- [CSV input contract](docs/input_contract.md): exact filenames/columns, decimal money, allocations and subledger semantics.
- [Three-minute demo and independent injection](docs/demo_runbook.md): fresh ZIP workflow, CLI backup, outage behavior and holdout evaluation.

## MVP scope and limitations

Publishable predicates: **excess settlement**, **payment contrary to documented delivery terms**, **prohibited benefit under supplied payment policy**, and **revenue contrary to documented recognition terms**. Each revalidates source records and requires its specific corroboration. Findings establish the stated discrepancy within supplied records, not legal guilt, authenticity, intent, or general proof that a supplier is fictitious. SAT status and graph cycles alone never produce an accusation. Amount categories are non-additive because service exposure can overlap excess settlement; observed returns and revenue overstatement are not cash loss. Shared return transfers are deduplicated within that category.

Independent bank discovery is capped at 10,000 examined edges and 128 candidates under the investigation deadline. Traces use four hops, 30 days, 100 output edges and 1,000 examined edges. Truncation is explicit. Q&A extracts current-case calculations, findings, checks, missing evidence and dispositions; unsupported topics abstain. It does not perform arbitrary counterfactual calculations. CSV v1 remains supported; optional v2 tables add contracts, dated ownership, attributed evidence, return policies/linkage, and sales/receivables. CFDI XML, official SAT fetching and authenticity verification remain out of scope.

Default API views and JSON/HTML exports mask identifiers and omit unrestricted text. The UI's **Reveal original values locally** action and explicitly marked full-evidence HTML export expose originals only on this local server. Both export formats include the audit trail. This prototype has no authentication: full-record access is an explicit local reviewer operation, not a security boundary against other users of the same machine.

This is a single-machine **local prototype**, without authentication or deployment hardening. Keep it bound to loopback. Eight dataset slots and two active investigations live in memory; restarting loses them. Export a case to retain it. CLI `--sqlite` optionally archives source evidence; durable/resumable investigations are not implemented.

Small synthetic holdout results do not establish production fraud accuracy. Rehearse live model availability and latency before the challenge demo.

### Verification in this checkout

The implementation was tested with Python 3.12. Tests use mocked model transport and do not consume your key. The extended offline evaluation uses 60 datasets over the frozen manifest in `tests/holdout_manifest.json`; exact totals and zero unsupported findings on these declared fixtures do not establish real-world accuracy. Live model performance remains unverified without a configured server API key.

Where npm is unavailable, this checkout was built with pnpm-installed dependencies using:

```powershell
pnpm --dir web install
node web/node_modules/typescript/bin/tsc -b web
node web/node_modules/vite/bin/vite.js build web
```

The pnpm workspace explicitly allows the standard esbuild install script. Vite's subprocess may need local sandbox permission. See [privacy and model controls](docs/privacy_and_models.md) for the current restrictions and diagnostics.

AI latency: the CSV controller prefers bundled local evidence inspection, followed by separate alternative and conclusion decisions. It requests up to twelve distinct leads per call and preserves validated queued actions on AI resume. The 180-second default remains bounded; provider timeouts still leave an explicitly incomplete case.
