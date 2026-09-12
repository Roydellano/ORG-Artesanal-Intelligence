# CSV input contract · v1

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
