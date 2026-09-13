# Official student-materials workflow

The current supplied pack (including `estate_csv.zip` support and `validate_format.py --estate-zip`) is preserved in `specs/student-materials/`. The official workflow supplements the original CSV workspace; do not confuse their formats.

## Estate formats — both accepted

**Pitch declaration: the system reads either judge form — `estate.db` (SQLite) or `estate_csv.zip`.** A ZIP is converted into the same checked SQLite structure (CLABEs, RFCs and ids stay text; empty cells become NULL), so both forms produce identical decisions. The replay archive stores that database.

Use Python 3.11+ with SQLite `deserialize` support (verified on Python 3.12). Eight ordinary tables and the official column names are required. Extra tables are never queried, attached databases and uploaded SQL are never executed, and views/virtual/generated-column substitutes are rejected. Imports are limited to 20 MB and 20,000 rows. Monetary columns become integer centavos; nullable ledger/contract amounts are visibility gaps. Core transaction ids, endpoints and dates must be supplied.

The audited company RFC is optional: when omitted it is inferred as the RFC on the most invoices. The company need not be in `vendors`; its bank account is then inferred as the payer on the most transfers to invoicing suppliers, and the case file says so.

```powershell
.\.venv\Scripts\python.exe -m forensic_auditor.official run path\to\estate_csv.zip --seed 123 --output tmp\judge-case
.\.venv\Scripts\python.exe specs\student-materials\forensic-auditor\validate_format.py --submission tmp\judge-case.json --estate-zip path\to\estate_csv.zip
.\.venv\Scripts\python.exe -m forensic_auditor.official replay tmp\judge-case.replay.zip --output tmp\replayed-case
```

The CLI writes judge JSON, standalone original HTML, masked HTML and a replay ZIP, and prints a **decision fingerprint** (hash of findings, leads and log). A repeat invocation with matching output, estate, seed, company and mode reuses the completed run; `--fresh` measures a new one. Two fresh runs differ only in wall-clock telemetry, so their fingerprints are equal. Replay reproduces the exact file with no network.

In the React **Overview**, use **Judge estate · official estate.db or estate_csv.zip**. Enter the seed, optionally the company RFC, upload, then investigate.

## How a finding is published

1. **Detectors open leads** from the eight tables: SAT 69-B list, supplier master data, invoice-to-payment matching, dated bank paths, approval tiers, CFDI status and payment method, collections.
2. **The investigator corroborates** each lead against specific records.
3. **The challenger** argues benign explanations; each argument is checked against records and recorded with the finding (`challenges`) or as the lead's closing reason (`closed_by: challenger`).
4. **The validator** re-checks every cited record, per-table peso reconciliation within 2%, entity support and trail continuity. Failures close the lead (`closed_by: validator`).

`proven` means the cited records fully show the rule breach (for example a definitive 69-B listing plus undocumented paid invoices, a direct supplier-to-employee transfer, a cancelled CFDI still in revenue). `probable` means a corroborated pattern with an inferred element (an inferred approval limit, an intermediary account).

Documentary evidence governs: when typed contract terms exist for a supplier, the matching records heuristic defers to them.

## Records predicates (no special contract format needed)

All thresholds are constants at the top of `forensic_auditor/official/audit.py` and are echoed in the JSON as `detector_settings`.

| Scheme | Publishes when | Challenger arguments that must fail |
| --- | --- | --- |
| `phantom_vendor` | Paid active invoices, no purchase order and no contract for the supplier, and either a **definitive** SAT 69-B listing (`proven`) or at least two independent red flags (`probable`): registered ≤120 days before first invoice, CLABE shared with another supplier, forwards ≥50% of receipts within 10 days, missing address/email, presumed listing. | Listing cleared; purchase documented by PO/contract; unpaid or refunded; thin records of a real new supplier. |
| `kickback` | A company payment to a supplier is followed within 45 days (up to four hops, amounts never growing) by a transfer to an account that **exactly** equals one employee's 18-digit CLABE. Claim = the funding invoice(s); employee receipt is stated in the narrative. | Same bank code only / account shared; not yet employed; reimbursement or travel reference; payment not tied to an invoice. |
| `round_tripping` | A company payment returns ≥80% to the company account within 90 days, through intermediaries or booked as a company sales invoice. Claim = the outgoing invoice(s). | Partial return; refund, credit-note or loan reference or loan contract; direct return from the same supplier with no sale; payment not tied to an invoice. |
| `threshold_splitting` | An approval limit is inferred (a round amount above which only certain approvers sign, extended to employees with the same job title). Orders to one supplier by one requester or for one purpose, each 50–100% of the limit, within 14 days, totalling at least the limit: three or more orders, or two within three days, all signed by one non-senior approver. | A senior approver signed; separate purchases close together; limit is inferred (stated). |
| `revenue_inflation` | A cancelled CFDI still credited to revenue after all reversals (`proven`), or active PUE sales never collected with at least two corroborations (customer absent from master data, newly registered, on the 69-B list, never paid anything). Uncollected-sale testing is skipped when under 50% of sales show collections. | Reversed; amount mismatch; PPD (deferred) terms; slow-paying real customer. |

Unmatched company payments are listed as leads (visibility gaps), never accusations.

## Documentary predicates (optional typed contract terms)

Literal JSON in `contracts.scope_text` is an implementation convention, **not a requirement of the student pack**. Arbitrary prose is retained but never interpreted as a rule. Every document has `type` and `valid_until`:

- `delivery_terms`: `invoice_uuid`, `payment_condition` (`delivery`, `advance`, `unconditional`), `witnesses` with `author`, boolean `delivered`, ISO `date`.
- `payment_policy`: `invoice_uuid`, `employee_benefits` (`prohibited`, `permitted`, `unknown`).
- `funding_terms`: `invoice_uuid`, `commercial_purpose` (`none`, `loan`, `refund`, `trade`, `unknown`).
- `purchase_policy`: decimal-string `approval_limit_pesos`, `authorized_approvers`, integer `aggregation_days` (1–30), `aggregate_by` = `vendor_requester_description`.

## AI, costs and offline fallback

Offline runs make zero model calls and cost MXN 0. AI scheduling uses the configured OpenRouter model with only random lead/session aliases, available actions, counts and local predicate booleans. It cannot generate accusations or bypass the gate; invalid responses, outages, cancellation or budgets yield incomplete cases. Uploaded estates cannot use a `:free` endpoint. AI cost uses provider-reported USD `usage.cost` and a user-supplied USD/MXN rate with its source (`--mode ai --usd-mxn-rate RATE --fx-source SOURCE`); missing billing data blocks judge JSON export rather than reporting zero. See [OpenRouter usage accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting).

## Generation and evaluation

```powershell
.\.venv\Scripts\python.exe -m tools.official_generate --seed 4242 --estate tmp\fresh-estate.db --csv-zip tmp\estate_csv.zip --answer-key tmp\evaluator-only\answer-key.json
.\.venv\Scripts\python.exe -m tools.official_evaluate --output tmp\official-evaluation
.\.venv\Scripts\python.exe -m pytest -q
```

`--style records` (default) builds judge-like estates: ordinary purchasing with POs and prose contracts, payroll, sales and collections, a company absent from `vendors`, 2–5 planted schemes (entangled when kickback and split purchases share a supplier) and ten decoys that trip each detector but are innocent (presumed listings, documented new suppliers, same-bank accounts, travel reimbursements, duplicate-payment refunds, genuine customer-suppliers, monthly recurring orders, director-approved orders, reversed cancellations, PPD receivables). `--style typed` builds typed-contract estates.

The generator and evaluator live in `tools/` and are outside the runtime import graph (a test walks the graph). Answer keys are written to separate files.

The evaluator reports only on frozen **reporting seeds 812007, 823009, 834011, 845013, 856017**. Detector constants were developed on **tuning seeds 101, 202, 303, 404, 505**. Seeds 710003–750019 and sweep seeds 900001–900020 were the first reporting set; they exposed two split-purchase defects and are now development data (their first-run results are in `docs/verification.md`). `results.csv` (records style) and `results-typed.csv` use the template columns; `results.md` adds determinism, company inference, CSV-ZIP equivalence and closed-by counts.

Both estate styles come from this project's own generator, which was written alongside the detectors. The numbers show the detectors work on the patterns and decoys modeled here. They do not establish accuracy on the judges' generator or real books.

## Three-minute rehearsal

Upload a fresh estate (0:00–0:20), investigate and open the case file (0:20–1:40), show one finding's money trail and adversarial review, then one declined lead's reason and closer (1:40–2:25), ask about a saved lead ID (2:25–3:00). Save the replay first and restore it with networking disabled.
