# Presentation summary: The Forensic Auditor

[Back to the README](../README.md)

## One-sentence pitch

The Forensic Auditor connects company invoices and bank movements into an evidence-backed case file, showing the calculation behind each supported finding and explaining why other suspicions were dismissed.

## Thirty-second introduction

"Invoice fraud can be hidden across suppliers, invoices and bank transfers. The Forensic Auditor brings those records together, follows the money and checks legitimate explanations before publishing a finding. The result is a case file with source evidence, a reproducible peso amount and reasons for rejecting unsupported leads. AI can guide the review and explain the case, while local code validates the evidence and calculations."

## Five-slide outline

| Slide | Put on screen | What to say |
| --- | --- | --- |
| 1. The problem | An invoice, a supplier and several disconnected payments. | "Audit teams need to connect records to understand a scheme and avoid unsupported accusations." |
| 2. Our approach | Load records → find leads → trace funds → check alternatives → validate → report. | "We connect the evidence, challenge the explanation and record the outcome." |
| 3. What we investigate | Phantom vendors, kickbacks, round tripping, split purchases and inflated revenue. | "The official workflow supports five scheme types through specific evidence rules. Missing evidence limits what we can conclude." |
| 4. Show the case | One finding, its money trail, calculation and a declined lead. | "Every published finding points to records. The case also explains why other leads were closed." |
| 5. Why it is useful | Traceability, exact calculations, masked AI context and offline replay. | "The goal is a case an auditor can inspect and reproduce. This is a local prototype tested on synthetic scenarios; real-world accuracy remains unestablished." |

Use a screenshot from an actual completed demo case on slide 4. Copy its amount and confidence label exactly; do not invent a result or describe invoice exposure as demonstrated cash loss.

## Three-minute live presentation

The timings below are a rehearsal plan, not measured performance. For a network-free demonstration, select offline investigation and **Offline case extraction** for questions.

### 0:00–0:20 — Introduce the problem and load the records

"Fraud can be hidden across ordinary accounting records. We built The Forensic Auditor to connect those records and explain what the evidence supports."

Upload a fresh official estate or load a fictional practice estate. Explain that an estate is a package of company records.

### 0:20–1:40 — Investigate and show the trail

"The application identifies leads, follows the money and checks alternatives such as refunds, legitimate loans and approved purchases. Local code validates the records and calculations before a finding is published."

Start the investigation. Open one completed finding and show its linked records and money trail. Name its scheme, confidence label and actual amount. State what that amount measures.

If using offline mode, say: "This demonstration uses deterministic offline review. Optional AI scheduling selects review steps under the same validation rules."

### 1:40–2:25 — Explain a finding and a rejected lead

"Here is the evidence behind this finding and the calculation supporting the amount. Here is an alternative explanation the system checked. This other lead was closed, and the case records why."

Open the finding's alternative checks and then a declined lead. Use the actual reasons displayed by the application.

### 2:25–3:00 — Answer a question and show the output

"An auditor can ask about the completed case, inspect the cited evidence and export the report. The official replay bundle reproduces the completed output without another model call."

Ask about an actual finding or lead ID. Show the answer and its references, then the report/replay download controls. Demonstrate network-free replay only if it has been rehearsed.

## Answers to likely questions

**What does AI do?**  
It can choose permitted investigation steps and explain a masked case. Local code owns the evidence checks and amount calculations; generated explanations cannot change the validated findings.

**Does it work without AI?**  
Yes. Offline evidence review and offline case extraction require no model calls. That is a separate, clearly labeled mode.

**How do you reduce false accusations?**  
The rules require linked evidence and check benign alternatives. The case records declined and inconclusive leads. This reduces unsupported conclusions within the implemented rules; it is not a guarantee.

**What does "proven" mean?**  
The supplied records satisfy the implemented rule. It is an application label, not a legal determination or proof that the source records are authentic.

**What data can it read?**  
The official workflow accepts estate.db or estate_csv.zip in the supplied hackathon schema. An earlier CSV workflow has its own separate contract.

**How is sensitive information handled?**  
Identity matching and source evidence remain local. External model context is masked and restricted. Uploaded records cannot use the free model; offline review or enforced no-collection/zero-data-retention routing is required. Masking does not remove every disclosure risk.

**Why use the optional blockchain feature?**  
The Devnet seal supports checking whether a sealed report changed. It does not establish that the underlying accounting records or findings are true.

**What are the limits?**  
The prototype cannot infer invisible cash transfers or authenticate source documents. It has no production authentication, and its evaluation uses project-generated fictional records.

## If you include evaluation results

Use [pitch facts](pitch_facts.md) and [recorded verification](verification.md), keeping the declared reporting seeds, dataset scope and caveats alongside any numbers. Do not describe synthetic results as accuracy on real companies or the judges' hidden records. Offline timings do not measure live AI response time.

## Before presenting

- Rehearse the exact dataset and mode; keep a fresh dataset ready for the actual challenge.
- Confirm every amount and confidence label against the exported case.
- Prepare one supported finding and one declined lead to explain.
- Select offline Q&A when presenting without provider configuration.
- Export the case and replay bundle before restarting the server.
- Rehearse voice, AI and Devnet separately if including those optional features.
