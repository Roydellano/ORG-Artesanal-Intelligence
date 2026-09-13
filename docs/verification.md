# Implementation verification — September 12, 2026

## Records-based detection, CSV ZIP estates and seed rotation

Changes: records-only predicates for all five schemes (no typed contract terms needed), per-finding challenger review, `proven`/`probable` confidence, `closed_by` on every lead, `estate_csv.zip` ingestion, company RFC/account inference, decision fingerprint, updated student-materials pack (validator `--estate-zip`), legacy answer-key modules moved to `tools/legacy/`.

- Full suite: `.venv/Scripts/python.exe -m pytest -q` — 140 passed, 3 subtests. New tests cover records-only estates (all five found, no decoy accused, validator passes, no typed terms present), clean records estates, CSV ZIP = SQLite fingerprint plus `--estate-zip` validation, same-bank-code non-ownership, reimbursement references, replay with sockets disabled, and nullable ledger money.
- Before this change, replacing typed contract JSON with prose on estate 710003 left only `revenue_inflation` detected. After it, the records predicates find all five on prose-only estates.
- **First reporting run (now retired):** seeds 710003–750019, records style: 19/19 schemes, **1/50 decoys accused** (seed 750019: director-approved split orders treated as unapproved because that director never signed above the limit), peso amounts not reconciled for that seed. Typed style: 19/19, 0/50. A 20-seed sweep (900001–900020): 94/94, 0/200, one split cluster cut by an unrelated earlier order (seed 900013).
- Both defects were fixed (senior approvers extended by job title; clustering on near-limit orders only). Those 25 seeds became development data and a new reporting set was frozen before running.
- Development set after fixes (tuning + retired, 30 seeds): records 144/144, 0/300; typed 144/144, 0/300; all amounts reconcile.
- **Reporting run, seeds 812007/823009/834011/845013/856017:** records 19/19 schemes, 0/50 decoys, all amounts reconcile, company inferred correctly, reruns identical, CSV ZIP identical; typed 19/19, 0/50. Offline: 0 LLM calls, MXN 0, 0.18 s total investigation time for five records estates. Output: `tmp/official-evaluation/results.md`.
- CLI end-to-end on a generated `estate_csv.zip` without `--company-rfc`: company inferred, five findings, the supplied validator with `--estate-zip` passed, and replay reproduced the HTML byte-for-byte.
- Not done: the frontend was not rebuilt because Node.js is not on PATH in this environment; `web/dist` predates the `.zip` upload and optional-RFC changes in `web/src/OfficialEstate.tsx`. Run `npm --prefix web run build` before demoing the UI. No live model call or timed human rehearsal was performed.

All estates come from this project's generator, written alongside the detectors. These results show behaviour on the modeled patterns and decoys, not accuracy on the judges' estates.

## Official student-materials increment

- Full suite: ` .venv/Scripts/python.exe -m pytest -q` — 116 tests and 3 subtests passed. Two existing Starlette/httpx deprecation warnings remain.
- TypeScript: `node web/node_modules/typescript/bin/tsc -b web` passed; `node --test web/tests/*.test.mjs` passed both frontend amount checks.
- Production build: `node web/node_modules/vite/bin/vite.js build web` passed. The sandbox initially prevented esbuild reading its configuration; the approved build outside the sandbox succeeded.
- Official validator: ` .venv/Scripts/python.exe specs/student-materials/forensic-auditor/validate_format.py --submission tmp/official-final.json --estate tmp/official-evaluation/estate-710003.db` passed, including source existence and per-table peso reconciliation.
- Official evaluation: ` .venv/Scripts/python.exe -m tools.official_evaluate --output tmp/official-evaluation` reported 19/19 schemes found and 0/50 decoys accused across five reserved seeds. Claimed and actual scheme totals both equal MXN 352,858.67. This is a scheme-level matching total, not a deduplicated cash loss. `results.csv` uses the supplied column order, and `manifest.json` names tuning/reporting sets and scope. Offline runs have zero model calls and MXN zero inference cost; measured investigation time totals approximately 0.007 seconds on these small in-process fixtures, excluding ingestion, export, browser and live inference.
- CLI run and replay completed using `tmp/official-final.replay.zip`. Regression tests verify exact submission/HTML reproduction, no network calls, source removal, forged arithmetic/citations/dispositions, conflicting ownership, partial payments, refunds, contradictory delivery, cancellation, invalid databases, masking and malformed AI actions. AI transport/cost tests use a mock provider and a declared test FX rate.
- Browser verification on local port 8012 uploaded reporting estate 710003 through the file chooser, completed with five findings and 17 declined leads, displayed rendered diagrams and answered a saved lead question with citations. Visual inspection prompted clearer evidence-specific decline reasons and corrected per-record noncash diagram amounts. The original-identity API/export/replay paths are covered by the end-to-end API test.

No live model request or timed human three-minute rehearsal was performed for this increment. The browser reports that server configuration contains a key and an effective model; the earlier no-key note below is historical, not a fresh configuration claim. Unknown contract prose and unsupported accounting semantics are documented limits on unseen estates. Passing these fictional fixtures is not production fraud accuracy.

## Earlier CSV workflow verification

Environment: local Windows checkout, Python 3.12.0, Node.js v24.19.0, Vite 6.4.3. Frontend dependencies were installed with pnpm because npm was not available on PATH. The existing 43 tests passed after restoring dependencies; the final expanded suite contains 96 passing tests plus 3 unittest subtests. Two dependency deprecation warnings from Starlette/httpx remain; no failing tests were suppressed.

| Check actually run | Result |
| --- | --- |
| `.venv/Scripts/python.exe -m pytest -q` | 96 passed, 3 subtests passed |
| `node web/node_modules/typescript/bin/tsc -b web` | Passed |
| `node web/node_modules/vite/bin/vite.js build web` | Production build passed; sandbox permission was needed for the build subprocess |
| `.venv/Scripts/python.exe -m forensic_auditor.evaluate --output tmp/holdout-evaluation.json` | Original 20 datasets: 10 expected findings, zero false positives/negatives, all exact amounts and valid citations |
| `.venv/Scripts/python.exe -m forensic_auditor.evaluate --extended --output tmp/extended-evaluation.json` | 60/60 completed, 60/60 exact category totals, all citations valid, zero unsupported findings |
| `git diff --check` | Passed |

The extended frozen manifest uses five reserved seeds, six scenario families and positive/benign variants. Each fixture has 54–76 source rows and goes through public upload, investigation, case export and deletion routes. There are 40 expected findings across excess settlement, service terms, prohibited returns, revenue recognition and combined cases. Each supported family achieved fixture precision/recall of 1.0; the benign cycle family has no expected finding, so its finding precision/recall is undefined. Internal flows with dated same-company ownership are dismissed; unresolved external flows remain inconclusive.

Measured offline API times on this small workload: p50 0.0465 seconds, p95 0.078 seconds, maximum 0.094 seconds. These numbers are in-process API timings, not browser upload timings, large-dataset benchmarks, or live-model latency. Tests include hand-authored revenue data independent of the generator, forged serialized findings, missing/contradictory records, repeated sources, expired ownership, currency/path inconsistencies, shared-return totals, privacy canaries in captured transport, malformed/truncated model outputs, cache/session isolation, and deletion while work is in flight.

Browser checks used the locally built app on loopback port 8011:

- Loaded the multi-scheme fictional demo and inspected four findings and separate amount categories.
- Followed a masked citation to a source row and explicitly revealed original fictional values locally.
- Asked a question about evidence that could change a service finding. Browser inspection found overly broad answers and derived IDs in answer text; both received fixes and regression tests.
- Generated an independent clean estate (seed 88217), injected multiple schemes (seed 18779), and uploaded the resulting 74-row ZIP through the browser file chooser without exposing evaluator truth to the application. The investigation completed with four findings.
- Checked the visible model configuration and connection action: the page reports `Set OPENROUTER_API_KEY in .env.` instead of an unexplained investigation failure. No live provider request was made without credentials.

The graph source selector's `bank:<masked record alias>` format is covered by a regression test against the evidence API, alongside direct masked citation resolution. Both JSON and HTML exports include the audit timeline; API tests exercise masked and explicit original evidence access.

## Remaining verification limits

This checkout has no `.env` API key. The user's exact authenticated Nemotron error, live JSON behavior, free-tier rate limits, completion latency, billing and a full timed three-minute AI rehearsal remain unverified. The client now uses the verified Nemotron model slug, configurable output budgets and reasoning controls, explicit privacy routing, schema-validated actions, and sanitized errors, but this is not evidence of a successful live request.

Synthetic results establish behavior only on the declared contracts/fixtures. They do not establish production fraud accuracy, document authenticity, regulatory compliance, or a guarantee of zero false accusations on arbitrary company books. Source authenticity, generalized accounting import, full tax semantics, production access controls and durable resumable storage are outside this local prototype.
