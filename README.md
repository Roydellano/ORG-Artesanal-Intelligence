# The Forensic Auditor

**Follow the money. Check the evidence. Explain the finding.**

The Forensic Auditor helps finance and audit teams investigate suspicious activity in a company's accounting records. It connects invoices, payments, suppliers and supporting records into a case file that explains what happened, which records support it, how the peso amount was calculated, and which suspicions were dismissed or remain unresolved.

Built for the **HackMTY 2026 Infosys challenge**, this is a working local prototype. It helps a reviewer assess supported accounting findings; it does not establish legal guilt or guarantee that every fraud scheme will be found.

New to the project? Start below. Presenting it? Use the [presentation summary and three-minute script](docs/presentation_summary.md). Configuring it? See the [technical setup guide](docs/setup.md).

## Why this project exists

A suspicious invoice rarely tells the whole story. A reviewer may need to connect it to a supplier, check the bank payment, follow later transfers, and decide whether a refund or another legitimate explanation accounts for the activity.

This application brings those checks together. Each finding includes the supporting records and calculation, while rejected and inconclusive leads remain visible with their reasons.

## How it works

1. **Load the company's records.** Upload a supported file or choose a fictional demo. The app checks its structure and keeps references to the source records.
2. **Find leads.** Rules look for patterns worth investigating, such as payments linked to suspicious suppliers or money returning to the company.
3. **Connect the evidence.** Local tools match records, identify documented account relationships and follow dated money movements.
4. **Challenge the explanation.** The investigation checks alternatives such as refunds, legitimate loans, approved purchases or reversed accounting entries.
5. **Validate the finding.** Code checks the rule, evidence references, relationships and amounts. Missing support can close a lead or limit the conclusion.
6. **Review the case.** Explore the money trail, inspect evidence, read the calculation, ask questions and export the result.

For example, imagine a fictional supplier receives a company payment and later transfers money to an employee's bank account. The official workflow checks the invoice link, transfer dates, exact account ownership and possible reimbursement explanations. Sharing a bank name is insufficient. The report distinguishes the invoice amount supporting the claim from the amount the employee received.

## What it can investigate

The official hackathon workflow implements checks for five scheme types. Publication depends on the specific evidence rules in the [official workflow guide](docs/official_estates.md).

| Scheme | Plain-language meaning | Records the investigation connects |
| --- | --- | --- |
| Phantom vendor | A supplier may be billing without a supported purchase or delivery. | Paid invoices, supplier details, purchase orders, contracts and supplied SAT status. |
| Kickback | Money paid to a supplier may reach an employee. | Invoices, dated transfers and exact employee bank-account matches. |
| Round tripping | Money leaves the company and returns through a suspicious route. | Outgoing payments, intermediary transfers, returning funds and possible refund or loan explanations. |
| Threshold splitting | Related purchases may be divided to avoid higher approval requirements. | Order amounts, dates, requester, supplier and documented or inferred approval limits. |
| Revenue inflation | The books may show revenue that the supplied records do not support. | Invoice status, revenue entries, reversals and customer collections. |

A **lead** is a suspicion to investigate. A **finding** has passed the implemented evidence checks. Official findings use **proven** when the records establish the implemented rule breach and **probable** when an element is inferred. These are application confidence labels, not legal judgments.

## What the reviewer receives

- **A case file:** findings, linked entities, confidence and limitations.
- **An evidence trail:** source-record references and diagrams of money movements.
- **A reproducible amount:** the calculation and supporting records. Invoice value, returned money, exposure and loss are different measures and must not be added indiscriminately.
- **Investigation decisions:** alternative explanations checked and reasons for closing or leaving leads unresolved.
- **Questions and answers:** explanations grounded in the current case, with evidence references.
- **Exports:** JSON for structured data and readable HTML reports. The official workflow also provides a replay ZIP that reproduces the completed report without new model calls or network access.

## Where AI fits

The accounting checks run locally in Python. In **AI investigation mode**, a model accessed through OpenRouter chooses permitted review actions within time and step limits. It cannot bypass the evidence validator or rewrite the accounting rules.

**Offline evidence review** runs without a language model or API key. It is explicitly labeled as offline review. Model failures leave an AI investigation incomplete.

**Ask the Auditor** has its own mode selector: conversational AI explains a masked version of the case, while **Offline case extraction** retrieves supported information without network access. Choose offline extraction for a fully offline demo, even if the investigation itself already ran offline. Generated explanations do not change validated findings.

## Supported input formats

An *estate* means the collection of company records supplied for investigation.

| Workflow | Input | Use it for |
| --- | --- | --- |
| Official hackathon | estate.db (SQLite database) or estate_csv.zip (the official CSV tables in a ZIP) | The five scheme types above, judge-format JSON and offline replay. |
| Original CSV | A ZIP following this project's separate CSV contract | Excess settlement, documented delivery/payment violations, prohibited benefits and revenue-recognition discrepancies. |

The official format includes suppliers, invoices, ledger entries, bank transactions, purchase orders, contracts, employees and a supplied SAT list. SAT is Mexico's tax authority; its listing is supporting information that must be considered alongside company records.

The two formats are separate contracts; an arbitrary spreadsheet or ZIP will not necessarily load. See the [official estate format](docs/official_estates.md) and [original CSV contract](docs/input_contract.md).

## Try it locally

Install **Python 3.11+** with SQLite deserialization support and **Node.js 20.19+**. Python 3.12 has been used for this project. From the repository folder, run these commands in PowerShell:

~~~powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm --prefix web ci
npm --prefix web run build
.\.venv\Scripts\python.exe -m uvicorn forensic_auditor.api:app --host 127.0.0.1 --port 8000
~~~

1. Open [the local app](http://127.0.0.1:8000).
2. Drop `estate_csv.zip` into **Drop your company dataset here**, or click **Load demo** for fictional records.
3. Keep investigation mode offline and click **Start investigation**. Both inputs use the same workspace navigation and case views.
4. Open a finding, follow its money trail and inspect its evidence. Review a declined lead and its explanation.
5. Select **Offline case extraction** to ask about the completed case without configuring AI.
6. Download the report and replay bundle before restarting the server.

The seven practice estates cover the five individual schemes, a mixed scenario and a clean control. They are project-generated examples, not the judges' hidden data. See [practice files](demo-estates/README.md).

For development servers, AI configuration, voice and optional integrations, see [setup and technical reference](docs/setup.md). Command-line generation, official format validation and replay commands are in the [official estate guide](docs/official_estates.md).

## Privacy and optional features

Source records and identity matching remain local. External investigation scheduling receives a restricted, pseudonymous summary; conversational Q&A receives a separate masked case view. Masking replaces identifying details with aliases, but financial patterns and amounts can still be sensitive.

The configured free model is restricted to fictional datasets generated inside the app. Uploaded records require offline review or a non-free model with enforced no-collection and zero-data-retention routing. Keys stay in server-side configuration. See [privacy and model controls](docs/privacy_and_models.md).

Optional features include:

- **Voice questions through ElevenLabs:** spoken interaction for app-generated fictional demos. Microphone audio goes to the provider; voice requires separate configuration.
- **Tiger Data archive:** save masked completed analyses to PostgreSQL. It does not preserve original source files or resume investigations.
- **Solana Devnet integrity seal:** publish a fingerprint commitment that can help verify whether a sealed report changed. It does not prove the records or findings are true.

The app is a local prototype without authentication. Keep it bound to **127.0.0.1**. Active sessions are held in memory and are lost on restart; export the artifacts you need.

## Current limits and validation

The system implements specific evidence rules, not unrestricted fraud understanding. Missing transfers, uncertain ownership, undocumented commercial purpose and unfamiliar accounting semantics can prevent a supported finding. CFDI electronic-invoice XML signature validation, live SAT fetching, source authenticity checks and production deployment hardening are outside the current scope.

Automated tests and synthetic evaluations cover the modeled rules, benign alternatives, citations, calculations and failure handling. Results on this project's own generated records do not establish accuracy on real companies or unseen judge datasets. Authenticated live AI latency, billing and the timed human demo require separate verification.

Developers can run:

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests -q
npm --prefix web test
npm --prefix web run build
.\.venv\Scripts\python.exe -m tools.official_evaluate --output tmp/official-evaluation
~~~

Use only the evaluator's frozen reporting seeds for held-out claims. See [recorded verification](docs/verification.md) and [pitch facts with evaluation caveats](docs/pitch_facts.md).

## Project map

| Location | Purpose |
| --- | --- |
| [web/](web/) | React and TypeScript browser interface, built with Vite. |
| [forensic_auditor/](forensic_auditor/) | Python backend, local evidence tools, validation, reporting and FastAPI endpoints. |
| [forensic_auditor/official/](forensic_auditor/official/) | Official estate ingestion, five scheme checks, judge reports and replay. |
| [tools/](tools/) | Fictional dataset generators, separate answer keys, evaluators and setup utilities. |
| [tests/](tests/) | Backend and domain verification. |
| [specs/student-materials/](specs/student-materials/) | Supplied hackathon formats and requirements. |
| [docs/](docs/) | Input contracts, setup, privacy, verification and presentation material. |

The [challenge brief](HackMTY_2026_Infosys_Challenge_Forensic.md) defines the problem. The [implementation plan](IMPLEMENTATION_PLAN.md) records delivery status and design history. [AGENTS.md](AGENTS.md) contains contributor guidance.
