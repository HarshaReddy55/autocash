# Implementation Guide

AutoCash product pack, document 4 of 8. Previous: Architecture and System Design. Next: Deployment Guide.

## 4.1 Module-by-Module Code Map

### Backend Modules (`autocash/backend/app/`)
* **`api.py`:** Defines all FastAPI routes, session middleware (`X-Workspace-Session`), Pydantic validation models for policy and inline ledger edits, atomic approval handlers, and diagnostics endpoints.
* **`batch.py`:** Implements the six-agent pipeline, evidence-priority payment sorting, single-customer and currency filtering, auto-post settlement transactions, and per-agent timing telemetry.
* **`solvers.py`:** Implements `solve_milp` (the primary solver) and `solve_greedy` (the permanent evaluation baseline), tries the Rust kernel first on plain payments, counts distinct exact subsets for the ambiguity rule, re-verifies every returned set in exact integer cents with cuts and bounded retries, and records each result's objective terms and confidence derivation. The why-not counterfactuals are computed arithmetically from the same derivation data, without re-solving.
* **`rust_bridge.py`:** Invokes the compiled `autocash-kernel` binary over stdio with a JSON payload (`best_subset_rust`); `best_subset_py` is the reference implementation the 203-case equivalence suite compares it against. When the binary is absent the MILP decides, and the diagnostics view states which mode the system is in.
* **`reference_engine.py`:** Extracts invoice and purchase order references (`INV-`, `PO-`, `SI-`, `BILL-`, `DOC-`) and performs edit-distance-1 OCR character repair verified against open ledger IDs.
* **`fuzzy.py`:** Computes Jaro-Winkler string similarity and resolves learned payer aliases from the workspace `aliases` table.
* **`anomaly.py`:** Computes customer-specific deduction z-scores using the customer's historical ledger invoices and prior deductions (falling back to a baseline prior only when a customer has fewer than 3 historical records).
* **`erp_sap.py`:** Constructs SAP S/4HANA `BAPI_ACC_DOCUMENT_POST` JSON/XML payloads and ASC 606 / IFRS 15 EBRR reserve schedules.
* **`mail.py`:** Generates four live streams of outbound emails tied to active run records:
  1. Short-Pay and Unearned Discount Dispute Claims (with carrier POD citations, asserted only when the record shows a clean proof of delivery).
  2. Unidentified Wire / Exception Remittance Inquiries (for `NO_MATCH` and duplicate wires).
  3. SAP Settlement Confirmations (for `AUTO_POSTED` and `APPROVED` matches).
  4. Overdue Dunning Reminders (for unpaid open invoices remaining after reconciliation).
* **`forecast.py` & `ml.py`:** Computes an 8-week Monte Carlo cash forecast (P10/P50/P90) across the post-reconciliation residual ledger and ranks collector outreach by expected value using the validated payment delay model (MAE 2.95 days against a 7.67-day naive baseline, AUC 0.846; the model trains on a disclosed synthetic generator and is retrained on real history when available).
* **`ingestion.py`:** Fingerprints CSV column layouts, maps header synonyms (`inv_no`, `bill_no`, `doc_id`, `remit_text`), normalizes locale numbers, validates discount percentages (0% to 50%), and quarantines negative or malformed rows with reasons.
* **`ai.py`, `briefing.py`, `copilot.py`:** Manages Gemini API extraction with source-text amount verification, deterministic fallback parsing, executive run summaries, and workspace-grounded Q&A.
* **`repository.py` & `tenants.py`:** Manages SQLite `WAL` connections (`busy_timeout = 5000`), atomic match status updates, audit trail hashing, and LRU session eviction (128 ephemeral session cap).

### Frontend Modules (`autocash/frontend/`)
* **`index.html` & `css/livecube.css`:** Defines the top workspace bar, the horizontal navigation bar across all 14 views, slide-over drawers, shimmer skeletons, and dark-mode enterprise styling.
* **`js/state.js`:** Manages client session UUIDs, API fetch wrappers, lazy tab rendering, and centralized workspace state synchronization.
* **`js/operate.js`:** Renders views `01 Dashboard`, `02 Use Cases`, `03 Upload Center`, `04 Run Reconciliation`, `05 SAP BAPI & EBRR`, and `06 Outbound Mail Hub`.
* **`js/insight.js`:** Renders views `07 Ledger` (with inline cell editing), `08 Forecast and Collections`, `10 Evaluations`, `11 Agent Health`, `12 Methodology`, and `13 Architecture`.
* **`js/assist.js`:** Renders views `09 Policy Studio` (with scratch-copy simulation preview), `14 Product Thinking`, and the floating workspace Copilot.

## 4.2 Key API Contracts

| HTTP Method & Path | Purpose | Key Behavior & Guarantees |
| :--- | :--- | :--- |
| `GET /api/v1/workspace` | Hydrate active session state | Returns staged/settled invoices, payments, active policy, and latest run summary. |
| `POST /api/v1/cases/{id}/load` | Stage a benchmark or demo case | Resets session tables and loads raw invoices and payments in `STAGED` state without pre-solving. |
| `POST /api/v1/batches` | Execute 6-agent reconciliation | Runs unsettled staged payments, settles `AUTO_POSTED` invoices atomically, and returns agent timings and matches. |
| `POST /api/v1/matches/{match_id}/decision` | Maker-Checker approval or rejection | Body: {decision: approve or reject}. Atomic compare-and-set transition out of `PROPOSED` (a second concurrent decision gets a conflict); settles invoices in full, or reduces the open balance on a partial payment and records the partial application; saves the learned alias; issues the SAP `DZ` document number. |
| `GET /api/v1/approvals` | The Maker-Checker queue | Current `PROPOSED` matches, newest first - including the zero-line `NO_MATCH` refusal, by design. Approving the refusal (via the decision route above) books it to Unapplied Cash Suspense (GL 119900) as `PARKED_SUSPENSE` with an audit entry, and creates no AR posting. |
| `PUT /api/v1/policy` | Update governance thresholds | Validates threshold ranges, records before/after values in the audit trail, and triggers optional re-evaluation. |
| `POST /api/v1/policy/preview` | Scratch-copy policy simulation | Clones workspace in memory and returns exact match shifts without mutating live session data. |

Additional contracts used across the product surface:

| HTTP Method & Path | Purpose | Key Behavior & Guarantees |
| :--- | :--- | :--- |
| `GET /api/v1/workspace` | Hydrate active session state | (above) plus the workspace state: empty, staged, or executed. |
| `POST /api/v1/workspace/run` | Execute reconciliation on the staged workspace | Pending payments only; re-execution returns the standing run instead of posting twice. |
| `GET /api/v1/runs/{run_id}/agents` | Per-agent run evidence | Status, measured time and evidence per agent, including the processing order used. |
| `POST /api/v1/import/file` | Import a remittance file | JSON body with base64 content; PDF text layer, PNG/JPG via OCR, plain text and email files. |
| `POST /api/v1/parse` | Parse remittance text | Response states its source (gemini or the deterministic parser), whether it degraded, and the ledger verifier's findings. |
| `GET /api/v1/erp/run-documents` | The run's SAP posting pack | Every cleared document with run totals; balanced by construction. |
| `GET /api/v1/forecast` | Cash forecast | Computed only from the post-reconciliation residual ledger. |
| `GET /api/v1/evaluations` | Solver benchmark | MILP accuracy against the greedy baseline on labelled ground truth, computed per call. |
| `GET /api/v1/diagnostics` | Dependency and subsystem state | Kernel equivalence probe, AI state, mail state with the password redacted. |
| `GET /api/v1/docs` | This document pack | Served in flow order, PRD first. |

Until a mailbox is configured (the AUTOCASH_SMTP_* variables in the Deployment Guide), every mail send is recorded as `recorded_not_sent` with the reason shown; the product reports a mail as sent only when the SMTP server accepted it.

## 4.3 Verification and Automated Test Suite
The `backend/tests/` directory contains 134 automated tests across 29 `pytest` modules covering unit, integration, security, and UI contract checks:
```bash
python -m pytest backend/tests -q
```
Key test suites include:
* `test_audit_remediation.py`: Verifies idempotent re-runs, no double-posting, cross-customer/currency blocks, ambiguous tie detection, atomic concurrent approvals, discount parsing, and XSS escaping.
* `test_milp_solvers.py` & `test_rust_equivalence.py`: Verifies exact cent equivalence between the Rust subset-sum kernel and HiGHS MILP solver.
* `test_erp_documents.py`: Verifies that every generated SAP S/4HANA `BAPI_ACC_DOCUMENT_POST` document balances debits and credits to 0 cents with a non-null `CUSTOMER` ID.
* `test_refusal_parking.py`: Verifies that a `NO_MATCH` wire can never be approved into AR - approving its refusal parks it in suspense, and the only other route is a buyer inquiry.

---

Version 3.0 | 3 Nov 2026 | Owner: C. Harsha Vardhana Reddy
