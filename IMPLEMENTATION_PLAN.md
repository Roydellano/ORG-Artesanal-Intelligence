# Forensic Auditor implementation plan

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

