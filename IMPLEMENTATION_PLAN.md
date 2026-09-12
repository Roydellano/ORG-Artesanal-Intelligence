# Forensic Auditor implementation plan

## Implementation status — September 12, 2026

The updated execution plan below has been implemented in the existing package: typed model privacy projection; masked views and both exports with explicit local original access; dataset deletion; independent bounded flow discovery; v2 contracts/ownership/attestations/sales records; service-payment, prohibited-benefit and revenue-recognition predicates; per-category deduplicated amounts; audit exports; expanded extractive Q&A; multi-scheme fictional injection; and a versioned public-API holdout evaluator. The user changed the selected model to `nvidia/nemotron-3-ultra-550b-a55b:free`; `.env` still takes precedence through server configuration.

The free endpoint's published trial notice is incompatible with confidential/personal data. A documented implementation decision restricts free models to server-generated fictional demos; uploaded data uses offline review or no-collection/ZDR routing. No unsafe fallback, paid model substitution, or account privacy-setting change is performed. Token limits are configurable (2048 default), reasoning is disabled by default, and the UI includes sanitized effective configuration and a fixed-prompt connection check.

Validation: the restored legacy suite passed before the domain extensions; the expanded suite and frontend build pass. The 60-dataset offline API holdout completed with exact category totals and valid citations, with zero unsupported findings on its declared benign controls. Browser checks cover multi-scheme investigation, masked evidence and local reveal. These are synthetic acceptance results, not production fraud accuracy. See `docs/verification.md` for the final recorded check counts and limitations.

Remaining external verification: this checkout has no `.env` or API key, so the user's original authenticated Nemotron error and live completion/latency/cost cannot be reproduced here. The model client handles the identified compatibility failure modes, but no live success is claimed. Free-tier availability and a complete timed AI rehearsal remain unverified. Arbitrary counterfactual Q&A, source authenticity checks and broader accounting semantics remain outside the implemented narrow predicates; incomplete/unsupported evidence results in abstention.

The historical sections below are retained as design history. This status and the current input/model documentation govern claims about shipped behavior.

## Updated execution plan — September 12, 2026

This section is the prioritized plan for the existing implementation. It supersedes the ordering and conflicting implementation proposals in the original roadmap below. It is a plan, not a statement that the changes have shipped.

Requirements come from the original [challenge brief](HackMTY_2026_Infosys_Challenge_Forensic.md) and the user's September 12 event/Q&A update: explain findings through the data trail, avoid false accusations, handle injected synthetic fraud, and secure/mask sensitive financial identifiers before external inference. The update permits synthetic/open datasets and describes free AI model options; it does not clearly establish a mandatory zero-cost rule. Preserve the selected OpenRouter integration, verify eligibility and costs before rehearsal, and do not silently change models. Preserve the original brief unchanged.

Interpret the requested "chain of thought" as a reproducible audit explanation: hypothesis, tool action, source evidence, checked alternatives, rule outcome, amount calculation, and disposition. Do not request, store, or present private model reasoning as evidence.

### Baseline and scope

Code review found a working architectural slice for excess settlement, source provenance, bounded investigation, upload, case views, exports, and extractive Q&A. It also found unmasked tool results in outbound model context, no enforced provider data-use policy, invoice-only lead generation, and no publishable rule for fictitious services, kickbacks, or fabricated sales. Circular transfers can be traced after another lead triggers investigation, but do not independently generate leads.

The review could not execute verification: the documented `.venv` and frontend dependencies were absent, `npm` was unavailable on PATH, and available Python runtimes lacked required packages. Existing tests and evaluation code are coverage assets, not fresh passing results.

Keep FastAPI/Pydantic, React/TypeScript/Vite, NetworkX, exact centavos, CSV ingestion, and the deterministic evidence gate. Work in the actual `forensic_auditor/`, `web/src/`, and `tests/` directories; a broad repository reorganization is unnecessary. No model training, production deployment, OCR, or general tax engine is part of this increment.

| Requirement | Current gap | Delivery gate |
| --- | --- | --- |
| Explainability | Limited Q&A; printable HTML omits full timeline | Phase 4: linked audit explanation in UI and both exports |
| No false accusations | Strong gate for one rule only | Phase 3/5: rule-specific alternatives, evidence-removal tests, benign controls |
| Injected schemes | Excess-payment injector; one generator family | Phase 5: independent fixtures, multiple schemes, same upload interface |
| PII security | Raw identifiers and tool fields can leave server | Phase 1: allowlisted model projection and verified transport tests |
| Provider data use | No enforced routing/privacy contract | Phase 1: verified eligible routing, no unsafe fallback |
| Multi-transaction investigation | No independent flow leads; narrow rule coverage | Phase 2/3: bank-rooted leads and corroborated scheme predicates |
| Model/data resources | Synthetic generation exists; live eligibility/cost unverified | Phase 0/5: documented model configuration and measured live rehearsal |

### Phase 0 — Establish a reproducible baseline

**Touchpoints:** `requirements.txt`, frontend dependency lockfile, `README.md`, existing tests and evaluator.

1. Prepare the documented Python environment and frontend dependencies. Run the existing test suite, holdout evaluator, and frontend build; record actual commands, tool versions, failures, and runtime.
2. Preserve the existing offline fixture results as a regression baseline. Verify fresh upload-to-export behavior before changing contracts.
3. Record the configured model ID without credentials. Verify current provider API fields, data-use/retention terms, model availability, and event cost eligibility from official sources during implementation. Treat these as unresolved dependencies until checked.

**Done when:** setup is reproducible, baseline failures are resolved or explicitly tracked, and the implementation has a documented external-inference eligibility check. Do not send customer records during baseline verification.

### Phase 1 — Protect data before any external model call

**Touchpoints:** new `forensic_auditor/privacy.py`, `investigation.py`, `openrouter_client.py`, `api.py`, `reporting.py`, `web/src/App.tsx`, new privacy/transport tests.

1. Separate the local source store from a typed model-facing projection. Keep original bytes, RFC matching, account ownership joins, and evidence validation local. Outbound messages may contain only allowlisted facts needed for tool selection.
2. Allocate opaque, collision-checked aliases per dataset session for entities, accounts, invoices, transactions, leads, and evidence. Do not derive aliases using plain hashes of low-entropy identifiers or use last-four digits as join keys. Keep the reversible mapping in memory on the server; reject unknown or cross-session aliases in model responses.
3. Omit names, RFCs/SSNs, account numbers, original identifiers, filenames/URLs, descriptions, payment references, and unrestricted notes from external context. Replace useful text with local structured predicates and cited aliases. Apply the same policy to initial leads, every tool result, errors, cached context, and future Q&A calls. Use a final outbound validation gate that blocks unexpected fields before network I/O; regex redaction is supplemental, not the main boundary.
4. Retain amounts, currencies, relative timing, and relationship facts only where needed. Document the residual sensitivity of transaction patterns; pseudonymization is not a promise of anonymity.
5. Enforce verified provider restrictions for training/data collection and retention, including routing/fallback behavior. Record policy version and verification date. If eligible routing cannot be established, block external AI mode with an actionable reason; keep separately labeled offline review available. Do not invent provider API flags or assume transport encryption establishes no-training guarantees.
6. Mask identifiers in default UI views and shareable exports. Provide an explicit local source-inspection action and a clearly marked full-evidence export for reviewers; never pass that full export into model context. Keep technical privacy diagnostics in a sanitized server audit record. Add dataset deletion that clears records, jobs after safe cancellation, mappings, and caches; document separately created export/archive retention.
7. Preserve the loopback-only prototype boundary. Authentication and deployment hardening become prerequisites if network access is introduced; do not describe this phase as production security certification.

**Acceptance checks:** capture complete outbound HTTP request bodies with mocked transport after every tool type, and assert seeded PII canaries never appear. Include identifiers embedded in IDs, notes, references, URLs, Unicode text, exception paths, and Q&A submitted during a running investigation. Test alias consistency, collisions, session isolation, cache clearing, unsupported provider policy, and no automatic unsafe fallback. Verify local original evidence and exact amounts remain intact. Test default masked JSON/HTML exports as well as explicit full-evidence exports.

### Phase 2 — Discover schemes beyond invoice-triggered leads

**Touchpoints:** `data.py`, `engine.py`, `investigation.py`, `docs/input_contract.md`, graph/timeline consumers in `web/src/App.tsx`.

1. Introduce a typed lead contract with an independent lead ID, lead type, subject record references, hypothesis code, evidence references, missing facts, priority, state, and disposition. Migrate tools away from assuming every lead ID is an invoice ID. Version case/lead contracts and update API/UI consumers together.
2. Add bank-rooted, time-ordered cycle and pass-through lead generation independently of overpayment, SAT matches, and delivery disputes. Include unallocated bank movements as investigative candidates without guessing invoice attribution or account ownership.
3. Bound the entire discovery pass as well as individual traces by examined edges, depth, elapsed time, and candidate count. Start with existing trace limits (four hops, 30 days, 100 output edges, 1,000 examined edges per trace), add a dataset-wide work budget, and report truncated discovery explicitly. Check cancellation during discovery.
4. Rank and deduplicate related leads without discarding source references. Retain grouped paths for inspection; do not label a cycle as kickback proof or assume successive transfers contain the same pesos.
5. Add versioned input extensions only for the next rule's evidence needs. Preserve v1 uploads; reject ambiguous/unknown versions clearly. Ownership intervals, contracts/obligations, approval records, and service corroboration must identify their source and relevant dates. Missing new records must cause a narrower conclusion or abstention.

**Acceptance checks:** an otherwise balanced invoice estate containing an independent bank cycle produces a lead; a bank-only cycle with missing ownership remains inconclusive. Harmless treasury transfers and refunds do not become fraud findings. Test changed IDs, reordered rows, disconnected components, high-degree graphs, bounded execution, cancellation, and explicit discovery truncation.

### Phase 3 — Add evidence-backed scheme rules one at a time

**Touchpoints:** `engine.py` or focused rule modules, `data.py`, `investigation.py`, generator/injector, domain tests.

For each rule, define the required records, precise predicate, contradictory facts, benign alternatives, evidence set, amount type, and accounting formula before implementation. Recompute from original source bytes at publication. A model-selected action or narrative cannot substitute for a missing predicate.

| Order / rule | Required corroboration and alternatives | Permitted conclusion and amount |
| --- | --- | --- |
| 1. Preserve excess settlement | Existing invoice, obligation ledger, allocations, owners; credits, refunds, cancellation, unallocated amounts | Existing excess-settlement exposure; never automatically intent or loss |
| 2. Payment contrary to service terms | Contract ties payment to delivery; invoice and bank settlement; independently sourced records establish non-delivery for the relevant period; check advances, milestones, disputes, credits, and refunds | Payment inconsistent with documented service terms; eligible net paid exposure, not all supplier spend or automatic proof of a fictitious company |
| 3. Corroborated prohibited return of funds | Observed ordered bank legs, dated recipient ownership/relationship, source-linked rule prohibiting the payment or benefit, and documented transaction linkage; exclude refunds, loans, reimbursements, authorized distributions, internal transfers | Verified prohibited payment/return under supplied terms; report observed return separately from initial outflow and exposure; do not infer tracing through commingled funds |
| 4. Unsupported recorded sale | Versioned customer/sales/receivable records, recorded recognition, applicable supplied recognition condition and independently sourced contradiction; check credit sales, timing, returns, credits, and cancellations | Revenue recorded contrary to documented conditions; reversible overstatement amount, separate from cash loss; unpaid invoices alone are insufficient |

The sales rule needs a separate receivables contract; do not reinterpret the current supplier-obligation subledger as sales evidence. Each rule remains unavailable for substantiation until its contracts and controls pass. Distinguish independent source evidence from repeated assertions copied across files; source hashes do not establish authenticity.

Add case-level accounting for overlapping findings. Track claimed portions of source allocations, preserve separate amount categories and currencies, and avoid summing the same exposure twice across rules. If overlap cannot be resolved, show separate non-additive amounts instead of an invented grand total.

**Acceptance checks for every new rule:** positive fixture, benign lookalike, missing required evidence, contradictory evidence, uncertain/expired ownership, forged reference, amount tampering, partial refund, and overlap with another rule. Removing essential evidence must downgrade/reject publication. Findings state the supported discrepancy and visibility limits; use fraud/scheme language only to the extent supported by the implemented predicate.

### Phase 4 — Make the investigation defensible on screen and in exports

**Touchpoints:** `investigation.py`, `reporting.py`, `api.py`, `web/src/App.tsx`.

1. Store structured audit events: lead/hypothesis, action, supporting/contradicting evidence, alternative tested, outcome, rule version, missing facts, and disposition. Generate concise explanations from validated facts/templates. Any optional model paraphrase must remain limited to validated claims and citations.
2. Define required tool checks per lead/rule type. Replace the universal invoice-reconciliation prerequisite for bank/sales leads with appropriate prerequisites. Preserve schema validation, repeated-call detection, bounded calls, cancellation, and incomplete outcomes.
3. Show a clear path from scheme summary to related transactions, exact calculation, tested alternatives, and source rows. Make graph truncation and missing external legs visible. Include the full audit timeline and calculation context in both JSON and printable HTML, respecting the privacy modes from Phase 1.
4. Extend Q&A to selected findings/entities: why flagged, why another lead was dismissed, how an amount was calculated, which records support a relationship, what remains unknown, and what evidence would change the conclusion. Prefer extractive responses and typed read-only retrieval. Counterfactual calculations are labeled hypothetical and never alter published findings. Any added model call uses Phase 1's boundary.
5. Distinguish completed review of generated leads from complete fraud coverage. Show implemented rule coverage, unexamined/truncated regions, deferred leads, and incomplete investigation state.

**Acceptance checks:** UI and exports agree on claims, totals, dispositions, and audit events; every citation resolves locally. An unfamiliar supported question retrieves the right finding and references, while unsupported intent/ownership questions abstain. Prompt injection through a model-facing field or question cannot create tools, disclosures, or unchecked findings. Rehearse the full interaction in the actual browser.

### Phase 5 — Evaluate hidden injections and rehearse the challenge

**Touchpoints:** `demo.py`, `inject.py`, `evaluate.py`, `tests/`, `docs/demo_runbook.md`, `README.md`.

1. Extend independent injection to each implemented scheme and benign lookalike, using fictional entities only. Maintain evaluator truth outside uploaded records, model context, tool outputs, and exports. Do not leak scenario names or expected outcomes through metadata.
2. Freeze a versioned holdout manifest before tuning. Include hand-authored fixtures that do not share the detector's reconciliation logic, multiple simultaneous schemes, cycles with no invoice anomaly, varied topology/dates/amounts, and missing or contradictory evidence. Fresh seeds from one generator alone do not establish generalization.
3. Run all fixtures through the same public upload/investigation/export API. Separately run browser rehearsals and a declared live-model subset after privacy gates pass. Mocked controller tests do not count as live-model validation. Verify fresh dataset isolation without code changes or presenter access to expected answers.
4. Report lead recall separately from substantiated-finding precision/recall, unsupported supplier accusations, expected abstentions, exact amount accuracy by category/currency, citation validity, completion rate, p50/p95/max runtime, model calls, and cost. Count incomplete cases and discovery truncation explicitly rather than excluding them.
5. Rehearse: 0:00–0:20 upload an unseen compatible dataset; 0:20–1:40 investigate; 1:40–2:25 explain a supported finding and a rejected lead; 2:25–3:00 answer a judge-selected question. Declare the tested dataset size and machine. Target completion within 90 seconds; optimize measured bottlenecks while preserving validation. Outages remain incomplete AI investigations; offline review is an explicit separate mode.

**Release gates (targets, not achieved results):**

- Zero seeded PII canaries in outbound requests and default shareable artifacts; verified provider eligibility with safe failure behavior.
- All published findings have valid citations, satisfied predicates, and exact reproducible amounts; zero unsupported accusations on the declared benign/ambiguous suite.
- Every implemented scheme is detected and correctly disposed in its reserved acceptance fixtures. Publish holdout misses and metrics by scheme without implying production accuracy.
- Fresh upload, evidence inspection, export, cancellation, outage handling, and surprise Q&A work through the demo interface.
- Live completion/runtime/cost results are recorded on the declared demo workload; no claim of a successful rehearsal until executed.

### Delivery order and scope control

Implement as reviewable increments: baseline → privacy boundary → independent flow leads/contracts → service-payment rule → prohibited-return rule → sales rule → audit/Q&A completion → holdout and live rehearsal. Add tests and independent fixtures with each rule, not only at the end. Update README/input contracts when behavior ships; keep pending features marked planned.

If time runs short, preserve privacy, evidence validation, independent flow discovery, at least one fully corroborated new scheme, and the fresh-data rehearsal. Keep unfinished scheme families explicitly unsupported. Defer visual polish, official SAT fetching, CFDI XML, optional local-model adapters, durable storage, and additional export formats first. Do not advertise full challenge coverage while required scheme families remain unimplemented.

## Original roadmap and architectural context

The following material preserves the earlier design context. Its milestone descriptions are targets; the updated execution plan above governs new work and corrects obsolete ordering or scope assumptions.

## Objective and current state

Build the HackMTY 2026 Infosys "Forensic Auditor": an agent that investigates unfamiliar company records, follows money across entities, produces evidence-backed findings with MXN amounts, explains discarded leads, and answers a judge's follow-up question.

Source: `HackMTY_2026_Infosys_Challenge_Forensic.md`, converted from the supplied one-page PDF extract, printed page 3 of 5. A local MVP is implemented; the status below distinguishes it from the broader milestones. This plan assumes a local hackathon prototype; team size, hardware, and event duration are not specified. Milestones are ordered by dependency rather than promising an unverified deadline.

## Current delivery and agreed changes

- **User-selected frontend:** bare React + TypeScript + Vite replaces Streamlit. FastAPI exposes the Python tools and serves the built bundle. No hosting/deployment is introduced.
- **Implemented:** strict ZIP/CSV contracts, exact centavos, SHA-256/row provenance, fictional seeded generation and separate injection CLI, excess-settlement rule with refund/credit/allocation alternatives and independent source-byte revalidation, source inspector, transfer graph, timeline, lead dispositions, JSON and escaped printable HTML exports.
- **Controller:** OpenRouter chooses typed actions from a fixed registry. Reconciliation and alternative checks are mandatory before a deterministic conclusion. Budgets, timeout, repeat detection, cancellation, dataset/model/prompt/context caching and incomplete states are implemented. Zero retries is the MVP retry cap. Offline mode uses the same tools/gate but is separately labeled.
- **Finding scope:** corroborated excess settlement only. Supporting-record disputes, SAT entries and observed cycles remain leads. Broader fictitious-service, fabricated-sale and kickback predicates remain unfinished.
- **Data subset:** gross invoice total/credit, invoice-obligation subledger, explicit allocations, ownership assertions for the uploaded period, optional support/SAT rows. Full CFDI, dated ownership intervals, raw credit notes and general-ledger importing are deferred. See `docs/input_contract.md`.
- **Storage:** capped in-memory active sessions. CLI optionally archives provenance to SQLite; durable normalized records, resumable cases and persistent audit events remain planned.
- **Q&A:** extraction of current-case totals, calculations, findings and dispositions with validated citations. Unsupported topics abstain; open-ended model-generated answers are deferred.
- **Evaluation:** domain/API tests plus 20 reserved synthetic datasets over ten seeds, including clean controls. Evaluation covers the implemented rule offline. Live model availability/latency and the full unseen-scheme challenge rehearsal remain separate release dependencies.

The sections below retain the full challenge roadmap. Their "Done when" statements are targets, not claims that every milestone is delivered.

## MVP scope and design decisions

- Inputs: supplier master, ledger, invoices, bank transactions, account ownership, and a dated SAT Article 69-B snapshot. Accept CSV first; add CFDI 4.0 XML ingestion after the vertical slice works.
- Investigations: invoice/payment inconsistencies, supplier risk corroborated by company records, and circular money flows. Include benign lookalikes and unsupported hypotheses.
- Outputs: an interactive case file, downloadable JSON and HTML, source-linked money-flow visualization, and grounded follow-up answers.
- Defer model training, Kaggle anomaly baselines, production deployment, authentication, OCR, and comprehensive tax compliance. They do not need to block the challenge demo.
- Use a single investigation controller with typed tools. The model proposes the next investigative step and writes explanations; deterministic code validates evidence and computes amounts.

Proposed stack: Python, Pydantic schemas, SQLite for normalized records and audit events, NetworkX for bounded graph traversal, bare React/TypeScript/Vite with FastAPI for the local dashboard, pytest for domain tests, and OpenRouter with the user-selected DeepSeek V4.1 Flash model. Load OPENROUTER_API_KEY and OPENROUTER_MODEL from a Git-ignored server-side .env file; default model ID: deepseek/deepseek-v4.1-flash. Validate responses locally and benchmark latency and tool selection before the demo. These are implementation choices, not requirements in the PDF.

Flow: upload -> validate and normalize -> generate leads -> investigate and challenge hypotheses -> validate findings -> render case file and answer questions.

## 1. Define contracts and build the data estate

Implement schemas before the agent:

| Record | Minimum fields |
| --- | --- |
| Supplier | internal ID, RFC, name, linked account IDs |
| Invoice | ID/UUID, issuer and recipient RFC, date, currency, subtotal, tax, total, cancellation/credit references when supplied |
| Ledger entry | ID, date, account, debit, credit, invoice/counterparty references |
| Bank transaction | ID, timestamp, source/destination account, currency, amount, payment reference |
| Account ownership | account ID, entity ID, source, validity dates if available |
| SAT record | RFC, published status, publication dates, snapshot date, source URL |
| Evidence | ID, input file hash, source row or XML location, normalized record IDs, tool/rule version |

Store currency amounts as integer centavos or Decimal. Normalize RFC formatting without fuzzy identity joins; preserve raw values and unresolved mappings. Keep non-MXN amounts separate unless a supplied, cited exchange rate supports conversion. Reject invalid records visibly and report dataset coverage. Support partial payments, consolidated payments, credit notes, and refunds in reconciliation; do not assume one invoice equals one payment.

Create a seeded synthetic company generator with ordinary transactions and independent scheme injection. Include supporting service/delivery records where a scenario requires evidence that invoiced work was not performed. Absence of such documents alone is insufficient proof.

Provide scenarios for duplicate/excess payments, a substantiated fictitious-invoice case, and time-ordered circular transfers, plus clean controls. Use fictional suppliers for injected fraud. Keep any real SAT data as a separately attributed public source, without fabricating transactions about real entities.

Keep ground truth in an evaluator-only file outside the agent's accessible records. Randomize identifiers, dates, amounts, graph structure, and seed; never expose scheme labels or generator metadata through investigation tools.

**Done when:** a clean and a seeded dataset load through the same public interface, every normalized row resolves to its source, and hidden labels are inaccessible to the agent.

## 2. Implement deterministic investigative tools

Expose narrow, validated tools rather than arbitrary model-generated SQL:

- `lookup_supplier`: company records, exact RFC matches, account mappings, and dated SAT status.
- `reconcile_invoices`: invoice-to-ledger-to-payment links, allocations, discrepancies, credits, and tolerances.
- `trace_funds`: directed, time-ordered paths within explicit depth and date limits, with transaction evidence.
- `check_supporting_records`: delivery/service evidence and contradictions, when available.
- `get_evidence`: retrieve cited source records.
- `test_alternative`: check supported benign explanations such as refunds, internal transfers, or partial settlement.

Each detector produces a lead with a rule ID, referenced records, priority, and missing evidence; it cannot directly publish an accusation. Bound graph searches to avoid cycle enumeration exploding on large datasets. A cycle is a lead, not sufficient proof of kickbacks. Company bank records alone may not reveal transfers between external suppliers: report that visibility gap instead of inventing edges.

Preserve SAT categories and dates. A listing supports the attributed status; it does not automatically establish that every company invoice is fraudulent or that its total is a tax loss.

**Done when:** fixture tests verify reconciliation and traces, while benign refunds, similar names, and incomplete ownership links do not become substantiated fraud findings.

## 3. Build the investigation loop

Represent each lead as `pending`, `investigating`, `substantiated`, `inconclusive`, `dismissed`, or `deferred`. Track the current hypothesis, supporting and contradicting evidence, missing facts, next action, and final disposition.

Controller loop:

1. Rank detector-generated leads.
2. Ask the model for a schema-valid hypothesis and one permitted tool call.
3. Validate tool arguments, execute, and record the result.
4. Ask for an evidence-based decision: pursue, change theory, test an alternative, or stop.
5. Submit proposed findings to the evidence validator.
6. Continue until lead exhaustion or the configurable step/time budget.

Use OpenRouter responses validated locally by Pydantic. The selected model advertises JSON output without JSON-schema enforcement; do not assume provider-side schema validation. Add tool calling and structured-response handling to the initial text client when implementing this loop. Add capped retries, repeated-call detection, timeouts, and cancellation. Cache using the dataset hash, model/version, prompt version, and tool arguments so fresh uploads cannot reuse stale evidence. A model outage must yield an explicitly incomplete investigation; detector output must not masquerade as a finished AI investigation.

Treat invoice descriptions and uploaded text as untrusted data, never executable instructions. Expose concise investigative decisions and tool results in the timeline rather than private model reasoning.

**Done when:** the agent follows a lead across multiple tools, abandons a dead end with an explanation, and finishes within a bounded runtime on the demo machine.

## 4. Enforce the evidence gate and calculate exposure

A substantiated finding must include:

- A precise claim and implemented rule whose conditions are satisfied.
- Explicitly linked supplier/entity identities.
- Retrievable evidence for every factual assertion.
- A reproducible amount calculation with supporting transaction IDs.
- Considered alternative explanations and material limitations.

Code checks record existence, relationship consistency, rule predicates, and arithmetic before publication. The model cannot override this gate. If evidence establishes only a discrepancy, report that discrepancy without upgrading it to intentional fraud. Inconclusive leads belong in a separate section.

Distinguish invoiced amount, paid amount, returned funds, estimated exposure, and demonstrated loss. Do not add each hop in a circular transfer as new loss, or count one payment twice across overlapping findings. Provide per-finding allocations and a deduplicated case total with its definition. Avoid computing tax liability without the required facts and a separately validated rule.

**Done when:** removing a required evidence record downgrades the finding, fabricated citations are rejected, and overlapping/circular scenarios produce exact expected centavo totals.

## 5. Deliver the investigation interface and case file

Case-file rendering formats only available integer-centavo amounts; missing or invalid values display as unavailable, never zero. Frontend regression checks run with `npm --prefix web test`. Rebuild with `npm --prefix web run build` after frontend changes so the API serves the current rule-specific calculation views.

Build four views:

1. **Dataset:** file upload, validation results, coverage, SAT snapshot date, and start/cancel controls.
2. **Investigation:** current lead, tool activity, evidence references, and evolving graph.
3. **Case file:** scheme summary, supported findings, entities, amount calculations, evidence tables, limitations, and dismissed/deferred leads with reasons.
4. **Ask the auditor:** questions answered from the current case and retrieved evidence; unsupported questions receive a clear statement of what is missing.

Clicking a graph edge opens its transactions; clicking evidence opens the original row/record. Follow-up questions may invoke read-only tools, with new results added to the audit log. Ensure displayed citations resolve before returning the answer. Export the same structured case to JSON and printable HTML; a dedicated PDF export is optional.

**Done when:** a reviewer can move from a finding to the calculation and original evidence, and the surprise-question workflow works without editing code.

## 6. Evaluate unfamiliar records and rehearse the demo

Freeze a holdout set before tuning. Measure scheme-level precision/recall, supplier false accusations, citation validity, amount accuracy, abstention on ambiguous cases, runtime, and tool/model calls. Report results by scenario; do not claim that synthetic success establishes production fraud-detection accuracy.

Required tests include clean but unusual suppliers, changing SAT statuses, duplicate inputs, split payments, credits, missing bank legs, uncertain account ownership, harmless cycles, overlapping findings, prompt injection in descriptions, invalid model JSON, and model timeout. Include an end-to-end test that uploads a newly generated dataset and validates the exported case against evaluator-only ground truth.

Proposed MVP release gates:

- Every published finding has valid source references, rule verification, and reproducible amounts.
- Zero unsupported accusations on the curated benign/ambiguous test suite.
- Detect and substantiate each implemented scheme in reserved demo fixtures, with precision/recall reported over randomized holdouts.
- Target investigation completion within 90 seconds on a declared dataset size and demo machine; measure and adjust scope before the live demo.

Three-minute rehearsal:

- 0:00-0:20: upload a fresh judge-provided dataset through the documented schema.
- 0:20-1:40: investigate while displaying source-linked activity and fund movements.
- 1:40-2:25: show the supported case, deduplicated MXN total, and one rejected lead.
- 2:25-3:00: answer an unexpected question with cited records.

Provide the input schema and an independent injection script so judges can change the scheme without code changes. Cache the attributed SAT snapshot, verify network access and OpenRouter credit, and rehearse using the configured external model. Test network failures separately and report an incomplete investigation when live inference is unavailable. Use a CLI path as a backup for UI problems, executing the same fresh-data investigation.

## Suggested repository layout

```text
src/forensic_auditor/
  schemas.py
  ingestion/
  data_store/
  detectors/
  tools/
  agent/
  evidence/
  reporting/
  ui/
scripts/
  generate_company.py
  inject_scheme.py
  evaluate.py
tests/
  unit/
  integration/
  holdout/
data/examples/
docs/input_contract.md
docs/demo_runbook.md
pyproject.toml
README.md
```

Implement the first vertical slice in this order: seeded duplicate-payment dataset -> ingestion -> deterministic reconciliation -> evidence gate -> minimal case export. Then add the agent's investigative choices, circular flows, corroborated supplier cases, UI, and holdout evaluation. If time becomes constrained, cut optional integrations and visual polish before cutting evidence validation or the fresh-data demo.

## External references checked during planning

- SAT's [Article 69-B consultation](https://wwwmat.sat.gob.mx/cs/Satellite?c=ConsultaInfo&childpagename=SatTyR%2FConsultaInfo%2FSAT_LandingConsultaInformacion&cid=1462228576674&packedargs=d%3DTouch&pagename=TySWrapper) provides access to the full list and describes published statuses. Preserve the source snapshot and status distinctions in the adapter.
- [IBM AMLSim](https://github.com/IBM/AMLSim/) generates synthetic banking transactions with known laundering patterns. Use it as an optional scenario source after the small company generator works; invoice/ledger integration still requires an adapter.
- [OpenRouter quickstart](https://openrouter.ai/docs/quickstart) documents the chat-completions endpoint and bearer authentication. [DeepSeek V4.1 Flash](https://openrouter.ai/deepseek/deepseek-v4.1-flash) is the user-selected model. Local schema and evidence validation remain required.

Before implementing the XML adapter, retrieve the official CFDI 4.0 schema and define the supported document subset explicitly. The user-selected OpenRouter integration requires an API key, available credit, and network access. The key must stay server-side and out of version control. The original challenge brief is preserved unchanged.

