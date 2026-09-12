# Three-minute MVP demo

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
- Cancel: prevents the next action. An in-flight remote request may take up to 25 seconds to return.
- Refresh/restart: the browser resets; API sessions live in memory, capped at eight datasets and two active jobs. Old idle sessions may be evicted. Export before leaving.
- No candidate lead under implemented rules does not prove absence of fraud.

## Evaluation

```powershell
.\.venv\Scripts\python.exe -m forensic_auditor.evaluate --output tmp/holdout-evaluation.json
```

Ten fixed evaluator seeds differ from unit/UI seeds. Each runs a mixed estate and clean control. Metrics cover only excess settlement, citations, exact amount, abstention and offline runtime. Small fixtures from one generator do not estimate production accuracy or establish detection of fictitious services, fabricated sales or kickbacks.
