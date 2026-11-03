# Architecture and System Design

AutoCash product pack, document 3 of 8. Previous: Market and Segment Research. Next: Implementation Guide.

## 3.1 High-Level System Architecture
AutoCash is engineered as a modular, four-layer system:
1. **Presentation Layer (`frontend/`):** A 14-page zero-build JavaScript application organized into three operational groups (`OPERATE`, `INSIGHT & GOVERNANCE`, `EVALS & ARCHITECTURE`) with lazy tab hydration, XSS-safe rendering, and optimistic UI updates.
2. **API and Isolation Layer (`backend/app/api.py`, `tenants.py`):** A FastAPI service providing REST endpoints under `/api/v1/*`, per-visitor workspace sessions carried by the `X-Workspace-Session` header (full UUID), LRU session cache management, and role-aware policy validation.
3. **Six-Agent Execution Layer (`backend/app/batch.py`, `solvers.py`, `rust_bridge.py`):** Orchestrates Capture, Linking, Matching, Deduction, Policy, and Briefing in sequence, ordered by payment evidence specificity.
4. **Persistence and ERP Layer (`backend/app/repository.py`, `erp_sap.py`, `mail.py`):** SQLite databases running in Write-Ahead Logging (`WAL`) mode with atomic compare-and-set transactions, paired with an SAP S/4HANA `BAPI_ACC_DOCUMENT_POST` generator and a four-stream Outbound Mail Hub.

```text
+-----------------------------------------------------------------------------+
|                        14-Page Enterprise Workspace                         |
|  OPERATE (01-06)    |    INSIGHT & GOVERNANCE (07-09)    |   EVALS (10-14)  |
+-----------------------------------------------------------------------------+
                                       |
                   HTTPS REST API (/api/v1/*) + X-Workspace-Session
                                       |
+-----------------------------------------------------------------------------+
|            Evidence-Sorted Six-Agent Orchestrator (batch.py)                |
|  [1. Capture] -> [2. Linking] -> [3. Matching] -> [4. Deduction]            |
|                               -> [5. Policy]   -> [6. Briefing]             |
+-----------------------------------------------------------------------------+
         |                             |                             |
+-----------------+         +---------------------+         +-----------------+
| Ingestion & AI  |         | Hybrid Math Engine  |         | ERP & Comms     |
| - Gemini Client |         | - Rust FFI Kernel   |         | - SAP S/4HANA   |
| - Regex Parser  |         | - Sparse HiGHS MILP |         |   BAPI + EBRR   |
| - Ledger Check  |         | - Uniqueness Probe  |         | - 4-Stream Mail |
+-----------------+         +---------------------+         +-----------------+
                                       |
+-----------------------------------------------------------------------------+
|       SQLite WAL Repository (Per-Session Isolation + Audit Trail)           |
+-----------------------------------------------------------------------------+
```

## 3.2 Evidence-Specificity Batch Ordering
In real lockbox batches, multiple wires from the same customer often arrive together. If an unreferenced wire is processed first, FIFO weighting might assign it an open invoice that a later wire in the same batch explicitly names by invoice ID.

To prevent this conflict, `batch.py` sorts all staged payments by **evidence specificity** before running the solver loop. Each payment carries an evidence rung, and the run sorts by it:

| Rung | Evidence | Meaning |
| :--- | :--- | :--- |
| 0 | `reference`, `po` | The wire names its invoices, or its purchase order |
| 1 | `ocr_reference` | The reference was recovered by OCR repair |
| 2 | `amount_payer`, `customer_ledger` | Payer and amount point at the customer's own ledger |
| 3 | `fuzzy_payer` | The payer matched by fuzzy name evidence |
| 4 | `all_ledger` | Nothing but a whole-ledger search |
| 5 | `none` | No usable evidence |

The order actually used is recorded in the Matching Agent's evidence for every run, so the processing sequence is itself auditable.

## 3.3 Mathematical Formulation of the Matching Engine

### Variables and Parameters
For a single payment of P cents and a candidate pool of n open invoices belonging to the same customer and currency, the problem has exactly 2n + 3 decision variables:
* I_i: Open balance of candidate invoice i in {1, ..., n} in cents (integer).
* discount_i = round(I_i x discount_rate_i): the early-payment discount available on invoice i, in cents.
* C: Claimed deduction amount on the payment in cents (0 when the payment claims none).
* x_i in {0, 1}: Binary decision variable equal to 1 if invoice i is selected (paid at gross I_i).
* d_i in {0, 1}: Binary decision variable equal to 1 if the discount on invoice i is taken (the invoice then settles for I_i - discount_i).
* take_claim in {0, 1}: Binary decision variable equal to 1 if the claimed deduction is accepted.
* s^+, s^- (continuous, >= 0): Non-negative slack variables representing unexplained underpayment (s^+) or overpayment (s^-) in cents. The residual is s^+ - s^-.

### Linear Constraints
1. **Cash Conservation Equation:**

```text
sum over i of (I_i x x_i - discount_i x d_i) - C x take_claim + s^+ - s^- = P
```

2. **A discount can only be taken on an invoice that is selected:**

```text
d_i <= x_i, for every i in {1, ..., n}
```

3. x_i, d_i and take_claim are binary; the two slacks are continuous and unbounded above, so the problem is always feasible and any unexplained cash is priced into the objective, never hidden.

### Objective Function

```text
minimise   1,000,000 x (s^+ + s^-)
         + 50 x (number of discounts taken)
         + 10 x take_claim
         - sum over i of w_i x x_i
where w_i = 1.0 + 0.05 x age_days_i
```

The residual weight dominates by six orders of magnitude: any set that explains the payment exactly beats every set that leaves a residual, whatever else it selects. The per-invoice reward w_i grows with invoice age, providing FIFO pressure toward older invoices without overriding exact cent conservation. The discount and deduction terms are small positive penalties, so the solver takes a discount or accepts a claim only when the arithmetic genuinely needs it. Every solved match stores its objective terms (the value of each term above, for the set actually chosen) and its confidence derivation, so a result can be explained term by term.

### Hybrid Rust + Sparse HiGHS Execution and Uniqueness Verification
1. **Rust Subset-Sum Kernel (`rust-kernel/`):** A compiled binary (`autocash-kernel`) invoked by `rust_bridge.py` over stdio with a JSON payload - not a shared library, and nothing is loaded through FFI. On plain payments (no discounts, no claimed deduction) it attempts the exact set first, and it decides the payment only when that set is provably the unique exact set. Its equivalence to the Python reference implementation is proven on a 203-case generated suite, and the diagnostics endpoint re-probes that equivalence live.
2. **Sparse HiGHS MILP (`solvers.py`):** Formulates the constraint matrix using `scipy.sparse.csc_matrix` with an explicit `time_limit` of 2.0 seconds and a relative gap tolerance of 1e-6, so large candidate pools never block a worker thread. A greedy first-fit matcher is kept permanently as the benchmark the solver must beat; the evaluations endpoint runs both over labelled cases.
3. **Uniqueness and Integrity Verification:** Whenever an unreferenced wire achieves an exact zero-residual match, the engine counts how many distinct invoice sets sum exactly to the payment (a bounded enumeration that stops at two: unique, or not unique). If a second distinct set also yields zero residual, `ambiguous_tie` is recorded, confidence is capped at 0.75, and the match is held as `PROPOSED` for human review. Separately, every set the MILP returns is re-verified in exact integer cents before it is believed - with seven-figure amounts, solver scaling tolerances can accept a set that is a few cents short - and a set whose true residual differs from the solver-reported one is cut from the problem and the solve repeats, at most 6 attempts, before an honest no-match is returned with a verification note.

## 3.4 Confidence Scoring and Governance Formula
Confidence is computed from evidence provenance and mathematical precision, never from zero residual alone:

```text
base = 1.0                                    if residual is 0
     = max(0.3, 1 - |residual| / payment)     otherwise

if the match came from an explicit reference or a purchase order:
    base = base + 0.03, at most 1.0

caps, applied last:
    ambiguous exact tie (section 3.3):  at most 0.75
    fuzzy_payer and all_ledger matches: at most 0.78
```

The caps are measured against the policy's automation threshold (0.90 by default): no weak-evidence match can reach the auto-post bar, however exact its arithmetic. Each match stores this derivation (base, bonus, cap, and the rule behind each) next to its objective terms.

* **Deduction Expected Value (EV) Formula:**

```text
EV = p(win) x Deduction Amount - Processing Cost
```

  where p(win) is a transparent heuristic - 0.94 when carrier Proof of Delivery is verified clean (`pod_verified_clean = True`), 0.35 otherwise - the processing cost is $45 by policy default, a dispute is auto-generated only when the proof of delivery is clean and EV exceeds the $100 minimum expected recovery, and claims at or below the $25 tolerance are written off without a dispute.

## 3.5 SAP S/4HANA (`BAPI_ACC_DOCUMENT_POST`) and ASC 606 EBRR Design
`backend/app/erp_sap.py` builds balanced double-entry clearing documents (`Doc Type DZ`, Company Code `1000`). The BAPI payload expresses each line with a debit/credit indicator (S/H); the journal lines are:

| Side | GL Account | Account Name | Accounting Treatment |
| :--- | :--- | :--- | :--- |
| **Debit** | `113100` | Cash - operating account | Exact cent amount of the incoming bank wire (P). |
| **Debit** | `415000` | Sales discounts allowed | Earned early-payment discount cents (the sum of discount_i over selected invoices). |
| **Debit** | `529000` | Deductions accepted (within policy) | A claimed deduction the policy accepts (within tolerance, or not worth contesting). |
| **Debit** | `121500` | Disputed receivables - deduction claims | Isolates contested short-pays while recovery is in flight; a matching ASC 606 / IFRS 15 dispute-reserve journal (Event-Based Revenue Recognition) is generated alongside each dispute claim. |
| **Debit** | `121600` | Residual receivable - part-paid invoices | Balances a partial payment so the unpaid balance remains open on the customer account, in the ledger and the forecast. |
| **Credit** | `121000` | Trade receivables - customer control | Gross open invoice cents cleared, each AR line tagged with the resolved `CUSTOMER` ID. |
| **Credit** | `121900` | Unapplied cash - customer on-account | The excess of an overpayment, held as the customer's on-account credit. |
| **Credit** | `119900` | Unapplied cash suspense | Used only to park an unmatched (`NO_MATCH`) wire whose refusal a controller approved; never a balancing plug. |

Every generated document enforces sum Debits - sum Credits = 0 in integer cents. Document numbers are deterministic: a cleared auto-posted match receives DZ-1400 plus 6 digits derived from the SHA-256 of its match ID, and an approved match receives DZ- plus the first 10 characters of its approval fingerprint, issued at decision time. Cleared documents carry the status STAGED_FOR_SAP_POSTING.

---

Version 3.0 | 3 Nov 2026 | Owner: C. Harsha Vardhana Reddy
