# The Forensic Auditor

HackMTY 2026 Infosys forensic investigation project. See [AGENTS.md](AGENTS.md) for project rules and [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for the roadmap.

Currently implemented: an OpenRouter text client and configuration. The web app and forensic investigation loop are still planned.

## Setup (PowerShell, Python 3.10+)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Create `.env` from `.env.example` if it does not already exist. A local `.env` has been prepared for this checkout. Fill it in:

```dotenv
OPENROUTER_API_KEY=your_openrouter_key
OPENROUTER_MODEL=deepseek/deepseek-v4.1-flash
```

The model ID is editable without code changes. System environment variables override `.env`. Keep the key on the Python server; never include it in browser code, logs, or case exports. Git ignores `.env`; commit only the empty-key `.env.example`.

## Check the API connection

After adding your key, run:

```powershell
.\.venv\Scripts\python.exe openrouter_client.py
```

This sends a small prompt to OpenRouter using the selected model and consumes API credit. It does not send project files or accounting records. The client has a 60-second network timeout and makes no automatic retries. Missing configuration, HTTP errors, and incomplete responses produce explicit errors.

The future application can call `chat(messages, max_tokens=1024)` from `openrouter_client`. This initial text client does not yet implement tool calling, structured investigation responses, evidence validation, or caching.

## Offline tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests mock the transport and never use your real key or make paid requests.

References: [OpenRouter quickstart](https://openrouter.ai/docs/quickstart) and [DeepSeek V4.1 Flash model](https://openrouter.ai/deepseek/deepseek-v4.1-flash).
