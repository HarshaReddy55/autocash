# Product Requirements Document

AutoCash product pack, document 1 of 8. Next: Market and Segment Research.

**Author:** C. Harsha Vardhana Reddy (IIM Visakhapatnam | NIT Andhra Pradesh)
**Platform Version:** Production Release v45
**Live Deployment:** https://au-060cf7bb8b42492097645654b34ab8d6.ecs.ap-south-1.on.aws/

## 1.1 Executive Summary
AutoCash is an autonomous Order-to-Cash (O2C) cash application and deduction recovery platform built for mid-market and enterprise finance teams.

Every business day, corporate treasury and accounts receivable (AR) teams receive bank wires and lockbox payments alongside separate remittance emails, PDFs, and spreadsheets. Analysts spend hours manually matching lump-sum payments to open invoices, investigating short-pays, keying clearing journals into SAP, and emailing buyers for missing remittance details.

AutoCash replaces manual spreadsheet reconciliation with a six-agent execution pipeline that:
1. Reads incoming remittance files and verifies every invoice and purchase order reference against the open AR ledger.
2. Links payments to the right customer across purchase order numbers, OCR typos, and subsidiary payer aliases.
3. Solves invoice allocation to the exact cent using a compiled Rust subset-sum kernel and a High-Performance Mixed-Integer Linear Programming (HiGHS MILP) solver.
4. Evaluates short-pays and unearned early-payment discounts using customer history and expected-value math.
5. Enforces maker-checker governance rules before posting to the general ledger.
6. Generates balanced SAP S/4HANA clearing journals and four streams of outbound customer emails.

## 1.2 Target Personas and Business Problems

| Persona | Daily Responsibility | Core Pain Point | AutoCash Outcome |
| :--- | :--- | :--- | :--- |
| **AR Cash Application Analyst** | Match daily lockbox wires to open invoices and clear exceptions. | Wastes 60% of the day hunting for missing remittance references, fixing OCR errors, and testing invoice combinations in Excel. | Routine and multi-invoice split wires post automatically; exceptions arrive pre-diagnosed with a ready-to-send buyer inquiry email. |
| **Corporate Controller** | Protect general ledger integrity, enforce SOX controls, and close the books on time. | High unapplied cash balances in suspense accounts at month-end and premature write-offs of valid revenue. | Every clearing journal balances debits and credits to $0.00, respects maker-checker dollar caps, and isolates disputed deductions under ASC 606 / IFRS 15. |
| **VP of Finance / Treasurer** | Maximize working capital, reduce Days Sales Outstanding (DSO), and forecast cash inflow. | Cash forecasts rely on stale ledger balances while hundreds of thousands of dollars sit unapplied or leaked in unchallenged deductions. | Live visibility into autonomous resolution rates, net cash posted, expected dispute recovery, and 30-day post-reconciliation cash inflow. |

## 1.3 Core Functional Requirements

### A. Two-Stage Execution Lifecycle (Staged to Reconciled)
To give operators and auditors complete visibility into what came in versus what the engine computed, every case follows a two-stage workflow:
* **Stage 1 (Staged Portfolio Readiness):** Loading a case or importing files stages the open invoices and incoming bank wires without running the solver behind the scenes. The Dashboard displays the exact raw portfolio waiting for execution (for example, $1,003,430.00 across 19 open invoices versus $682,135.00 across 16 incoming bank wires in the flagship demo case).
* **Stage 2 (Six-Agent Live Execution):** Clicking **Run Reconciliation** executes the six agents in sequence, records true millisecond timings and handoff payloads on a permanent audit strip, settles auto-posted invoices, and unlocks downstream SAP journals, outbound emails, cash forecasts, and evaluations.

### B. The Six-Agent Pipeline
1. **Capture Agent:** Extracts payer name, wire amount, payment date, invoice numbers, purchase order numbers, and claimed deductions from CSVs, pasted emails, `.eml` files, PDFs, and images. Uses Gemini when an API key is active and a deterministic regex parser as a fallback. A ledger verifier checks every extracted reference against open invoices so the AI can never invent a reference.
2. **Linking Agent:** Narrows the open ledger to candidate invoices for the payment using a five-step evidence hierarchy:
   * Step 1: Verified exact invoice IDs from remittance text.
   * Step 2: Verified purchase order (`PO-`) numbers mapped to open invoices.
   * Step 3: Levenshtein edit-distance-1 OCR character repair verified against open invoice IDs.
   * Step 4: Learned payer-to-customer aliases from prior controller approvals.
   * Step 5: Jaro-Winkler (0.88 threshold) fuzzy entity matching.
3. **Matching Agent:** Solves the integer-cent cash conservation equation across candidate invoices using the compiled Rust subset-sum kernel and sparse HiGHS MILP solver. Computes a plain-English mathematical derivation and a counterfactual proof explaining why unselected invoices for that customer were excluded.
4. **Deduction Agent:** Categorizes short-pays into the reason-code taxonomy (RC-02 Damaged/Shortage Claim, RC-05 Pricing Discrepancy, RC-07 Promotional Allowance, RC-09 Freight Claim, RC-11 Tax Withholding, RC-12 Unearned Discount, RC-99 Other/Unclassified), verifies carrier Proof of Delivery (POD) status, and calculates a deduction z-score against the customer's historical deduction behavior (a spike above 2.5 is flagged; below 3 historical samples a labelled baseline prior is used).
5. **Policy Agent:** Evaluates every solved match against four configurable governance rules:
   * Minimum confidence required for touchless auto-posting.
   * Maker-checker dollar threshold requiring human sign-off.
   * Minimum expected recovery value (EV) required to contest a deduction.
   * Maximum residual tolerance for automatic small-balance write-off.
6. **Briefing Agent:** Produces an executive run summary, prepares SAP S/4HANA clearing documents, and populates the Outbound Mail Hub.

### C. Financial and Accounting Guardrails
* **Integer-Cent Precision:** Every invoice amount, payment amount, discount, deduction, and SAP journal line is stored and solved in integer cents.
* **Single-Customer and Single-Currency Invariant:** A payment can never match across two different customers or across mismatched currencies (such as `EUR` against `USD`).
* **Ambiguous Subset-Sum Tie Protection:** When an unreferenced lump-sum wire can be satisfied by two or more distinct combinations of open invoices for the same customer, the solver detects the tie, caps confidence at 0.75, and routes the payment to human maker-checker review (`PROPOSED`) instead of guessing.
* **Strict Separation of Approvals and Exceptions:** Only valid invoice allocations held by policy thresholds (`PROPOSED`) can be approved into AR posting in the Maker-Checker queue. An unmatched wire (`NO_MATCH`) with zero linked invoices also sits in the queue, by design, but it can never post to AR: approving it parks the money in Unapplied Cash Suspense (GL 119900) with an audit entry and no posting document, and rejecting it routes it to a buyer remittance inquiry.

## 1.4 Product Surface (14 Dedicated Views)
* **OPERATE:** `01 Dashboard`, `02 Use Cases`, `03 Upload Center`, `04 Run Reconciliation`, `05 SAP BAPI & EBRR`, `06 Outbound Mail Hub`
* **INSIGHT & GOVERNANCE:** `07 Ledger`, `08 Forecast and Collections`, `09 Policy Studio`
* **EVALS & ARCHITECTURE:** `10 Evaluations`, `11 Agent Health`, `12 Methodology`, `13 Architecture`, `14 Product Thinking`

## 1.5 Target Benchmarks (Flagship 16-Payment Case)
* **Autonomous Resolution Rate:** 93.8% (15 of 16 incoming payments resolved with exact invoice math; 1 unknown-payer wire stopped safely as an exception).
* **Touchless Auto-Post Rate:** 62.5% (10 of 16 payments totaling $411,800.00 auto-posted straight through; 5 payments totaling $223,150.00 held for one-click maker-checker sign-off).
* **Dispute Recovery Identified:** $3,903.00 of expected recovery on the flagship dispute (a $4,200.00 shortage claim with verified clean proof of delivery, valued at the 0.94 win-probability heuristic net of the $45 processing cost). Unearned discounts are detected and claimed back by the same machinery (reason code RC-12).
* **Execution Transparency:** Every agent records its measured time and evidence on the run itself; the flagship batch's per-agent timings are inspectable on the Run page and in the Agent Health view, and no latency figure is claimed beyond what those records show.

---

## 1.6 Roadmap (labelled as roadmap, not product)
* **Model v2:** payment-delay and deduction-validity features drawn from the workspace's own payment and deduction history, replacing the population-level customer component - deliberately sequenced after real history exists to learn from, so the validated metrics above are not traded for an unvalidated model.
* **Save & Retrieve by Session ID:** named, restorable workspace sessions, so a reviewer can return to an exact workspace state by its session identifier.
* **ERP write-back and bank formats:** posting the staged DZ documents into a customer's SAP rather than staging them, and native BAI2 / MT940 lockbox ingestion alongside CSV.

Version 3.0 | 3 Nov 2026 | Owner: C. Harsha Vardhana Reddy

