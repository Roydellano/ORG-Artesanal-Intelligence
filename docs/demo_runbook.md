# Three-minute MVP demo

## Updated multi-scheme workflow

Overview now offers `all`, `excess`, `service`, `return`, `sale`, and `cycle` fictional scenarios. The clean-control checkbox supplies benign alternatives (permitted advances/reimbursements/unconditional recognition/refunds), not an absence of unusual transactions. `all` produces four supported discrepancy categories plus inconclusive flow leads. Change the seed before the presenter sees the data.

The selected free Nemotron endpoint works only with these app-generated fictional records. It logs use under its trial terms and is not an eligible route for uploaded financial records. A downloaded/re-uploaded ZIP is treated as an upload; use offline review or eligible no-collection/ZDR model routing for that path. Do not weaken privacy controls to make a live demo pass.

1. Upload an independently injected compatible ZIP for the judge-facing upload test, or load a fresh in-app fictional seed for the free-model demo. Keep evaluator truth separate.
2. Start investigation and inspect the graph and audit timeline. Every completed lead has a supported, inconclusive or dismissed disposition; truncated/outage cases stay incomplete.
3. Inspect the four separate amount categories. Do not sum exposure, observed returns and revenue overstatement. Open a masked citation, then explicitly reveal its original local source if appropriate.
4. Ask a case question such as “What evidence would change the service finding?” or select a finding alias in your question. Export masked JSON/HTML with the full audit trail.

Independent injection into a freshly generated fictional estate:

```powershell
.\.venv\Scripts\python.exe -m forensic_auditor.demo --seed 88217 --clean --output tmp/clean.zip
.\.venv\Scripts\python.exe -m forensic_auditor.inject tmp/clean.zip --seed 18779 --scheme all --output tmp/fresh.zip --truth tmp/evaluator-only.json
.\.venv\Scripts\python.exe -m forensic_auditor.evaluate --extended --output tmp/extended-evaluation.json
```

Use `--scheme service`, `return`, `sale`, or `cycle` for an individual new hypothesis; add `--benign` for legitimate lookalikes. The original excess injector remains the default. The extended evaluator uploads 60 datasets through the API using the frozen manifest, records incomplete outcomes, exact category totals, finding precision/recall and runtime, and deletes each session afterwards. `--extended --mode ai` requires eligible uploaded-data model routing and can consume credit; do not run it with a free-only configuration. Live cost/latency are not established by offline evaluation.

The browser checks in this checkout verified an offline multi-scheme case, masked citation lookup, explicit source reveal, and an independently injected ZIP through the upload control. Authenticated Nemotron testing remains pending because this checkout has no `.env` API key. The connection button reports this directly. See `docs/privacy_and_models.md` for exact model settings and provider errors and `docs/verification.md` for measured checks; a complete timed AI rehearsal is still pending.

## Original excess-payment example

Build the React app and start the API using README.md. Verify live OpenRouter availability separately before presenting AI mode.

1. **0:00–0:20 — Fresh records.** Generate a clean fictional estate and inject an excess payment using a seed the presenter has not seen. Upload `fresh.zip` in Overview. Never expose evaluator truth to the app.
2. **0:20–1:30 — Investigate.** Select offline review or configured AI mode and Start investigation. Inspect the timeline and a transfer using the graph's source selector. Show its original bank row and file hash.
3. **1:30–2:25 — Defend the case.** Open Case file, show payment-minus-refund-minus-obligation, inspect invoice/ledger citations, and explain an inconclusive or dismissed lead. Export HTML or JSON.
4. **2:25–3:00 — Follow-up.** Ask “How was the total calculated?” or “Why were leads dismissed?” Answers are extracted from this case. Other questions explicitly abstain; do not describe extractive Q&A as open-ended LLM reasoning.

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m forensic_auditor.demo --seed 7811 --clean --output tmp/clean.zip
.\.venv\Scripts\python.exe -m forensic_auditor.inject tmp/clean.zip --seed 91373 --output tmp/fresh.zip --truth tmp/evaluator-only.json
```

The injector only accepts fully settled invoices from suppliers explicitly named `(ficticio)`. It adds a payment and allocation; truth is written separately. Omit `--clean` from the generator to include refunded overpayments, split settlement, credit, disputed-delivery and dated-status controls.

CLI backup uses the same ingestion, controller and evidence gate:

```powershell
.\.venv\Scripts\python.exe -m forensic_auditor tmp/fresh.zip --output tmp/case-file
```

Add `--mode ai` for OpenRouter or `--sqlite tmp/evidence.sqlite` for optional local provenance archival.

## Failure behavior

- Invalid upload: fix the named schema/reference error. No partial dataset is accepted.
- AI timeout, invalid model response, repeated call or budget exhaustion: **incomplete**, with unresolved leads deferred. Published discrepancies remain explicitly part of a partial case.
- Cancel: prevents the next action and stops discovery. An in-flight remote request uses the configured 40-second default timeout (maximum 60).
- Refresh/restart: the browser resets; API sessions live in memory, capped at eight datasets and two active jobs. Old idle sessions may be evicted. Export before leaving.
- No candidate lead under implemented rules does not prove absence of fraud.

## Evaluation

```powershell
.\.venv\Scripts\python.exe -m forensic_auditor.evaluate --output tmp/holdout-evaluation.json
```

Ten fixed evaluator seeds differ from unit/UI seeds. Each runs a mixed estate and clean control. Metrics cover only excess settlement, citations, exact amount, abstention and offline runtime. Small fixtures from one generator do not estimate production accuracy or establish detection of fictitious services, fabricated sales or kickbacks.
