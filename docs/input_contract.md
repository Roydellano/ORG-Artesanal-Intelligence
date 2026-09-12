# CSV input contract · v1

Version 1 files remain valid. Optional v2 extensions are described below; each extension record requires `version=2`. Unknown columns/versions are rejected, not guessed. Neither a filename nor a record can declare an uploaded bundle trusted synthetic for free-model use.

Upload one ZIP with UTF-8 CSV files at its root. Required: `suppliers.csv`, `accounts.csv`, `invoices.csv`, `bank.csv`, `allocations.csv`, `ledger.csv`. Optional: `support.csv`, `sat.csv`. Unknown files, nested paths, duplicate filenames/IDs, invalid records, broken allocation references, and overallocated payments reject the whole upload. An empty file must still contain its header.

Limits: 20 MB compressed and uncompressed, 20,000 total records. Monetary fields are nonnegative decimal strings with at most two decimal places, no commas/exponents/symbols; maximum 1,000,000,000.00 per field. Bank and allocation amounts must be positive. IDs must be unique within their table. Text fields are bounded to 500 characters, descriptions/reference notes to 2,000. Uploaded text is data, never instructions.

Money becomes integer centavos internally and in API/JSON exports. Record and field limits keep aggregates within JavaScript's safe-integer range; React uses BigInt for formatting. No currency conversions occur.

Every file must have **exactly** these columns (order is flexible):

| File | Columns |
| --- | --- |
| suppliers.csv | `id,rfc,name` |
| accounts.csv | `id,entity_id,kind,source` |
| invoices.csv | `id,supplier_id,company_id,date,currency,total,credit,status,description` |
| bank.csv | `id,timestamp,source_account,destination_account,currency,amount,reference` |
| allocations.csv | `id,transaction_id,invoice_id,amount,kind` |
| ledger.csv | `id,invoice_id,date,account,currency,debit,credit` |
| support.csv | `id,invoice_id,status,source,notes` |
| sat.csv | `id,rfc,status,publication_date,snapshot_date,source_url` |

## Field meanings

- `accounts.kind`: `company`, `supplier`, `other`. Account IDs link to bank endpoints. `entity_id` must match the invoice's `company_id` or supplier's `id` for a finding. `source` identifies the supplied ownership assertion. v1 assumes the mapping applies for the uploaded period; it does not independently verify ownership or ingest validity intervals.
- Dates: ISO `YYYY-MM-DD`. `bank.timestamp`: ISO datetime **with a timezone**, e.g. `2026-08-01T10:00:00-06:00`.
- `currency`: uppercase three-letter code. An allocation's invoice/bank currency must match.
- `invoices.total`: gross invoice obligation including tax; subtotal and tax components are not separately modeled. `credit`: supplied credited amount, at most total. `status`: `active`, `cancelled`. Active obligation is `total - credit`; cancelled obligation is zero. Raw credit-note documents are not ingested; the net must be corroborated by the ledger.
- `ledger`: **invoice-obligation subledger**, not a full double-entry trial balance. `debit - credit`, summed per invoice, must equal its obligation after credits/cancellation. Do not upload both balancing legs of a general ledger as this subledger. `account` preserves the original account label.
- `allocations.kind`: `payment` (company → supplier), `refund` (supplier → company). Explicit allocations are required. A transaction can cover several invoices, but allocations cannot exceed its bank amount. Each transaction/invoice pair occurs at most once. Unallocated amounts remain visibility gaps, never guessed into an invoice.
- `support.status`: `delivered`, `not_delivered`, `unknown`. These are attributed assertions, not independent proof. Contradictions remain leads.
- `sat.status`: `presunto`, `definitivo`, `desvirtuado`, `sentencia_favorable`. Preserve every dated entry, including superseded statuses. Publication cannot follow snapshot. `source_url` retains attribution; v1 does not fetch/authenticate the snapshot. Demo statuses and `example.invalid` URLs are fictional, not official SAT data.

## Evidence gate

`excess-settlement-v1` requires an invoice, exact supplier identity, explicit allocations, consistent currencies, both account owners and a corroborating obligation ledger. Relevant unallocated transfers or missing ownership cause abstention.

`excess = max(0, allocated payments - allocated refunds - recorded obligation)`

The gate reloads original CSV bytes and checks the evidence set and arithmetic. Findings may cite one consolidated payment, but their allocations never overlap. Amounts are exposure against supplied obligations, **not demonstrated loss, intent, tax deductions or tax liability**.

Provenance includes file SHA-256, original strings, normalized record, CSV record number (header is 1), ending physical line for multiline CSV, and ingestion/rule versions. A hash establishes identity of supplied bytes, not authenticity or completeness.

Download the example from Overview, edit its CSVs and ZIP only the documented files. See `docs/demo_runbook.md` for independent injection. Keep evaluator truth outside the ZIP; the uploader rejects it.

## Optional v2 evidence contracts

Every table still uses the same source hash/CSV record/original value provenance. All columns shown are required when the table is supplied; an empty table has its header. Amounts remain decimal strings on input and integer centavos internally. Dates are ISO dates and intervals are inclusive. Source IDs and issuer IDs are supplied attribution, not certificates of authenticity.

| File | Exact columns |
| --- | --- |
| contracts.csv | `id,version,invoice_id,period_start,period_end,due_date,payment_condition,source_id` |
| attestations.csv | `id,version,subject_kind,subject_id,period_start,period_end,as_of,status,issuer_id,source_id` |
| ownership.csv | `id,version,account_id,entity_id,valid_from,valid_to,source_id` |
| return_policies.csv | `id,version,root_transaction_id,recipient_entity_id,valid_from,valid_to,disposition,purpose,source_id` |
| return_links.csv | `id,version,root_transaction_id,return_transaction_id,path,issuer_id,source_id` |
| customers.csv | `id,version,name,rfc` |
| sales.csv | `id,version,customer_id,company_id,date,period_start,period_end,currency,total,credit,status,recognition_condition,source_id` |
| sale_ledger.csv | `id,version,sale_id,date,currency,debit,credit,source_id` |

- `contracts.payment_condition`: `delivery`, `advance`, `milestone`. Only a single unambiguous delivery-conditioned contract can substantiate `service-terms-v2`. Its due date cannot precede period end. Payments before the due date require resolution rather than a service finding.
- `attestations.subject_kind`: `invoice`, `sale`. The subject must exist in the corresponding table. `status`: `delivered`, `not_delivered`, `unknown`. The period must exactly match the contract/sale, and `as_of` cannot precede period end. Corroboration needs at least two distinct issuers and source IDs, outside the transaction parties and contract/ledger sources, covering the payment/recognition date. A delivered assertion blocks the non-delivery predicate regardless of vote counts. Legacy delivered receipt assertions also block service publication until resolved.
- `ownership`: every relevant transfer endpoint needs an applicable dated ownership assertion matching `accounts.entity_id`. Conflicting applicable assertions or missing coverage block new service/return findings. Legacy excess settlement retains v1 period-wide account semantics.
- `return_policies.disposition`: `prohibited`, `permitted`, `unknown`. `purpose`: `benefit`, `refund`, `loan`, `reimbursement`, `distribution`, `internal_transfer`. The one applicable policy must identify the recipient entity and cover the full transfer period. Only an explicitly prohibited benefit is eligible; unknown or conflicting policies abstain. An explicit permission dismisses that policy hypothesis.
- `return_links.path`: a CSV-quoted JSON array of 2–4 distinct existing bank IDs, e.g. `["T1","T2","T3"]`. The first/last IDs must match root/return fields. Two distinct attributed linkage records must agree on the one path. Every leg must connect, increase strictly in time, use one currency, and fall within 30 days of the root. The origin must be a company account and the recipient cannot be the same company or another company-kind account. A return already allocated to an invoice remains unresolved. Linkage must not repeat the policy source or come from origin/recipient entities.
- `sales.recognition_condition`: `delivery`, `unconditional`. `status`: `active`, `cancelled`. Only active, delivery-conditioned records can substantiate the new revenue predicate. Cancellation requires additional reversal reconciliation. An unpaid sale alone is never proof.
- `sale_ledger` is a **revenue subledger**, separate from v1 invoice obligations: `credit - debit` is net recognized revenue. It must equal `sales.total - sales.credit` in the same currency. Debits include supplied reversals; a full double-entry ledger is not accepted as this subledger.

## Amount categories and limits

`service-terms-v2` measures net allocated payments contrary to delivery terms after refunds. `prohibited-return-v2` measures the observed recipient transfer once and reports original outflow separately; it does not attribute the same pesos through commingled funds. `recognition-terms-v2` measures net revenue recorded contrary to the supplied conditions. These are separate non-additive categories. No general fraud, tax or loss amount is inferred. Source identity and consistency are validated; factual authenticity and completeness are not independently established.

Independent bank discovery does not require an invoice anomaly. It also surfaces cycles and unallocated bank movements as inconclusive leads. Overall discovery limits are 128 candidates, 10,000 examined bank edges, and the case deadline. Traces are bounded to four hops, 30 days, 100 returned edges and 1,000 examined edges. Truncation makes the investigation incomplete.
