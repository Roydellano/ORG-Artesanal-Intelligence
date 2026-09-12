# Official student-materials workflow

The exact supplied pack is preserved in `specs/student-materials/`. The SQLite workflow supplements the original CSV workflow. Do not convert the official balanced general ledger into the legacy obligation subledger or claim that masked record aliases resolve against the judge's original database.

## Run an estate

Use Python 3.11+ with SQLite `deserialize` support (verified here on Python 3.12). Eight ordinary tables and the official column names are required. Extra tables are never queried, attached databases and uploaded SQL are never executed, and views/virtual/generated-column substitutes are rejected. Imports are limited to 20 MB and 20,000 rows, with bounded SQLite execution. Monetary columns become integer centavos for calculations. Nullable documentary fields remain visibility gaps; core transaction IDs, endpoints and dates must be supplied.

```powershell
.\.venv\Scripts\python.exe -m forensic_auditor.official run path\to\estate.db --seed 123 --company-rfc EMP920101AB1 --output tmp\judge-case
.\.venv\Scripts\python.exe specs\student-materials\forensic-auditor\validate_format.py --submission tmp\judge-case.json --estate path\to\estate.db
.\.venv\Scripts\python.exe -m forensic_auditor.official replay tmp\judge-case.replay.zip --output tmp\replayed-case
```

The CLI writes original judge JSON, standalone original HTML, masked HTML, and a replay ZIP containing the estate and completed submission. Store these local identity-bearing artifacts appropriately. A repeat invocation with matching output, estate hash, seed, company and mode reuses the completed run; `--fresh` explicitly measures a new run. Stable decisions are deterministic offline; elapsed time is measured rather than fabricated and varies in fresh runs. Replay preserves the exact original telemetry and case file. Replay is not a cryptographic authenticity guarantee; source and predicate validation checks internal consistency.

In the React **Overview**, use **Judge estate · official SQLite format**. Enter the seed and audited company RFC, upload the `.db`, then investigate. The official workspace has its own case, source inspector, saved-case questions and exports. The older CSV workspace remains separate. Original identifiers are hidden by default. Enable **Reveal original identities locally** for machine-checkable judge JSON, original evidence and replay download. Masked JSON is for review, not judge reconciliation. Upload a saved replay ZIP to restore a completed case after a server restart without network inference. Active sessions are in memory until explicitly exported; deleting a session does not delete downloaded artifacts.

## Evidence supported by each scheme

All five official `scheme_type` values are implemented, but each has a narrow corroborated predicate. Unsupported inputs produce declined/inconclusive leads; this is not a promise of discovering every hidden scheme.

| Scheme | Evidence necessary for the current predicate |
| --- | --- |
| `phantom_vendor` | Exact company/vendor ownership, one invoice-linked payment equal to invoice total, corroborating expense ledger, delivery-conditioned terms, two distinct nonparty non-delivery attestations covering payment, no contradictory delivery or refund. SAT status alone never suffices. |
| `kickback` | Connected strictly dated invoice-referenced bank path to one employee's exact CLABE, employment in effect, unambiguous sender ownership, one applicable contractual benefit prohibition, no conflicting permission/refund. Claim is original payment exposure; observed employee receipt is reported separately. |
| `round_tripping` | Invoice-linked time-ordered path back to the company's owned account plus one applicable supplied funding term explicitly excluding commercial purpose. A loan/refund/internal cycle by itself is not a finding. |
| `threshold_splitting` | Same vendor/requester/description order group, explicit aggregate approval limit/window and authorized approvers, every order below the limit, aggregate above it, and required approval absent. No default monetary threshold is assumed. |
| `revenue_inflation` | Cancelled outgoing invoice and net unreversed revenue equal to its total. Revenue names recognized are `Ingresos`, `Revenue`, `Ventas`, `Sales revenue`; debit reversals are subtracted, and balancing ledger entries are not added as revenue. |

The optional typed documentary convention is literal JSON in the existing `contracts.scope_text` column, with `vendor_rfc`, `start_date` and `value` preserved. This is an implementation convention, **not a new requirement imposed by the student pack**. No schema extensions or hidden scheme labels are required. Arbitrary prose is retained but not interpreted as an executable rule. Missing structured corroboration remains an explicit limitation on unseen estates.

Every document has `type` and `valid_until`. Supported additional fields:

- `delivery_terms`: `invoice_uuid`, `payment_condition` (`delivery`, `advance`, `unconditional`), `witnesses` containing `author`, boolean `delivered`, and ISO `date`.
- `payment_policy`: `invoice_uuid`, `employee_benefits` (`prohibited`, `permitted`, `unknown`).
- `funding_terms`: `invoice_uuid`, `commercial_purpose` (`none`, `loan`, `refund`, `trade`, `unknown`).
- `purchase_policy`: decimal-string `approval_limit_pesos`, `authorized_approvers`, integer `aggregation_days` (1–30), `aggregate_by` = `vendor_requester_description`.

Dates are ISO calendar dates. Conditions apply within their recorded validity interval. Multiple applicable documents prevent publication; attestations identify supplied authors, not authenticated independent witnesses. This prototype validates evidence consistency, not documentary authenticity. References are exact IDs with token boundaries; descriptions are not instructions. Unsupported currencies, tax calculations, general service-authenticity proofs, broad natural-language contract understanding and alternative charts of accounts are outside current detection scope.

## AI, costs and offline fallback

Offline runs make zero model calls and cost MXN 0. AI scheduling uses the configured OpenRouter model, only random lead/session aliases, available actions, counts and local predicate booleans. It cannot generate accusations or bypass the gate. It must complete inspection, alternative review and conclusion for each published lead. Invalid/out-of-order responses, outages, cancellation or budgets yield incomplete cases; offline candidates do not masquerade as completed AI work.

Cost-field integration was checked against [OpenRouter usage accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting). It measures reported request charges; credit-purchase fees and separately billed BYOK charges are not inferred from that field.

Uploaded official estates cannot use a `:free` endpoint, even when filenames say synthetic. Choose offline mode or explicitly configure an eligible non-free no-collection/ZDR model. No model switch or relaxation of privacy is automatic. AI cost uses provider-reported USD `usage.cost` and a user-supplied USD/MXN rate with its source/date. Missing provider billing data stays unavailable and blocks original judge JSON export, rather than reporting a fabricated zero. Supply rate/source in the UI or CLI `--mode ai --usd-mxn-rate RATE --fx-source SOURCE`. No live provider/billing success is implied by mocked transport tests.

## Generation, evaluation and demo

```powershell
.\.venv\Scripts\python.exe -m tools.official_generate --seed 101 --estate tmp\fresh-estate.db --answer-key tmp\evaluator-only\answer-key.json
.\.venv\Scripts\python.exe -m tools.official_evaluate --output tmp\official-evaluation
.\.venv\Scripts\python.exe -m pytest -q
```

The generator is outside the investigator's import graph and writes official-format answers separately. The application never imports it. The legacy demo now runs behind a records-only subprocess boundary as well; its answers never enter the API process. Do not upload evaluator answers or include them in inference context.

Evaluation writes `results.csv` with the supplied columns, a manifest naming tuning seeds 101/202/303 and reporting seeds 710003/720007/730013/740017/750019, estate/submission files and separate evaluator keys. The five reporting scenarios plant 2–5 schemes, include shared entities, vary identifiers/amounts/path lengths, and each contains ten decoys. The results table's claimed/actual amounts are scheme-level sums for matching, while the case executive summary deduplicates shared exposure bases. Neither is represented as demonstrated cash loss.

Three-minute rehearsal: upload a new estate (0:00–0:20), investigate and show the source-linked case (0:20–1:40), inspect a finding and a declined entity (1:40–2:25), ask about a saved lead ID and show its evidence/reason (2:25–3:00). Save the original replay first; restore it with connectivity disabled. Local offline automated verification does not substitute for a timed live AI/human rehearsal.
