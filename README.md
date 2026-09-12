# The Forensic Auditor

HackMTY 2026 Infosys forensic investigation project. See [AGENTS.md](AGENTS.md) for project rules and [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for the roadmap.

Working local MVP: **bare React + TypeScript + Vite** frontend and **FastAPI + Pydantic + NetworkX** backend. Includes ZIP/CSV upload with source provenance, seeded fictional records, independent excess-payment injection, exact reconciliation, evidence validation, supplier/SAT history checks, time-ordered fund traces, timeline, source inspector, JSON/printable HTML case exports and extractive case Q&A.

Offline review works without a model and is clearly labeled separately from AI investigation. OpenRouter can direct the bounded tool loop using the configured DeepSeek model.

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

## AI configuration

Create `.env` from `.env.example` if it does not already exist. A local `.env` has been prepared for this checkout. Fill it in:

```dotenv
OPENROUTER_API_KEY=your_openrouter_key
OPENROUTER_MODEL=deepseek/deepseek-v4.1-flash
```

The default model ID is `deepseek/deepseek-v4.1-flash`; availability depends on the provider. System environment variables override `.env`. Keep the key on the Python server; never include it in browser code, logs, or exports. Git ignores `.env`; commit only the empty-key `.env.example`.

Starting AI mode sends relevant uploaded record content to OpenRouter and consumes API credit. Only locally validated tool actions are accepted; the model cannot run SQL/shell commands or publish unchecked claims. Defaults: 36 steps, 90 seconds, at most 25 seconds per remote call, zero automatic retries. Invalid/repeated calls, premature conclusions, timeouts and exhausted budgets produce an incomplete case. Cancellation stops further actions after an in-flight request returns.

The per-investigation cache includes dataset hash, configured model ID, prompt version and complete tool context. It never crosses dataset sessions. Provider-internal model revisions are not observable/pinned.

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
npm --prefix web run build
```

Tests mock transport and never use your real key. They cover exact amounts, clean controls, split/consolidated payments, refunds/credits, ownership gaps, missing/forged citations, currency separation, bounded traces, SAT history, uploaded instruction injection, malformed responses, cancellation, dataset isolation and fresh upload-to-export API flow. Existing client tests also run with `python -m unittest discover -s tests -v`.

## Input and live demo

- [CSV input contract](docs/input_contract.md): exact filenames/columns, decimal money, allocations and subledger semantics.
- [Three-minute demo and independent injection](docs/demo_runbook.md): fresh ZIP workflow, CLI backup, outage behavior and holdout evaluation.

## MVP scope and limitations

The only publishable rule is **excess settlement against a corroborated recorded obligation**. It reports exposure, not intent, demonstrated loss or tax liability. Delivery disputes and circular transfers remain leads. SAT history alone never produces an accusation. Fund traces are capped at four hops, 30 days, 100 output edges and 1,000 examined edges; the graph shows the first 24 edges with explicit source selectors.

Q&A extracts supported totals, findings and dispositions, abstaining on other topics. CSV is a documented prototype contract, not a general accounting importer. CFDI XML, official SAT fetching, authenticity checks, dated ownership mappings, and validated fictitious-service/fabricated-sale/kickback rules remain future work.

This is a single-machine **local prototype**, without authentication or deployment hardening. Keep it bound to loopback. Eight dataset slots and two active investigations live in memory; restarting loses them. Export a case to retain it. CLI `--sqlite` optionally archives source evidence; durable/resumable investigations are not implemented.

Small synthetic holdout results do not establish production fraud accuracy. Rehearse live model availability and latency before the challenge demo.

References: [OpenRouter quickstart](https://openrouter.ai/docs/quickstart) and [DeepSeek V4.1 Flash model](https://openrouter.ai/deepseek/deepseek-v4.1-flash).
