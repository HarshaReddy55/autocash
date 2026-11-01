# AutoCash - Product Requirements Document
Version 1.0 | 31 Oct 2026 | Owner: C. Harsha Vardhana Reddy

## 1. Problem
Cash application (matching incoming payments to open invoices) is manual,
error-prone and slow in most mid-market finance teams. Industry context,
labelled as vendor claims and not AutoCash results: HighRadius markets 90%+
straight-through processing for its cash application cloud; manual remittance
handling is commonly costed around $7.82 per remittance in vendor literature.
Delayed application inflates DSO, distorts collections priorities and hides
deduction leakage.

## 2. Product thesis
Cash application is a conservation problem with an information problem on top.
Every cent must land somewhere auditable (conservation), but the evidence
arrives as messy remittance text (information). Therefore: probabilistic
components (LLM parsing, ML scores) PROPOSE; deterministic components (MILP
solver, accounting policy) DISPOSE. Anything unreconciled becomes a tracked
exception with a recommended action - never a silent write-off.

## 3. Users
- AR analyst: runs batches, works the exception queue, needs explanations.
- AR manager / approver: owns policy thresholds, approves high-value postings.
- CFO office: forecast and DSO visibility.
- IT / integrator: API keys, ERP import formats, audit exports.

## 4. Scope (built and test-verified in this repo)
1. MILP matching engine under a cash conservation equation (age-weighted,
   discount-penalised, residual-dominant) + greedy baseline + counterfactual
   "why was this invoice not chosen" explanations.
2. Rust matching kernel (subset-sum DP) with proven Python equivalence
   (203 shared cases) for the performance-critical path.
3. Batch orchestration: candidate restriction (references, PO, payer alias,
   subsidiary), matched-invoice consumption, duplicate payment detection,
   idempotent runs, per-step audit logs, maker-checker thresholds.
4. AI remittance parsing: Gemini structured extraction behind a deterministic
   verifier (every reference checked against the open ledger; invented
   references are flagged), with a deterministic parser fallback and explicit
   degraded mode.
5. Deduction intelligence: reason-code taxonomy with confidence, tolerance
   write-offs, z-score anomaly detection, dispute expected-value rule with
   transparent heuristics labelling.
6. ML services: payment-delay model and deduction-validity model trained with
   time-ordered holdout; metrics stored per version; cash-in forecast with
   P10/P50/P90 bands; collections prioritisation.
7. Grounded copilot: answers from product records with citations; refuses
   out-of-data questions; actions require confirmation.
8. Enterprise layer: multi-tenancy (database-per-tenant), API-key auth
   (hashed at rest), RBAC (viewer, analyst, approver, admin), tenant policies.
9. Operations: request IDs, structured JSON logs, Prometheus metrics,
   readiness checks, per-key rate limiting.
10. Product frontend connected to the live API (dashboard, run, ledger,
    parser, forecast, evaluations, copilot, product rationale).

## 5. Metrics (verified on labelled synthetic data in this repo)
- Evaluations: MILP match accuracy 100% vs greedy 80%; exact ($0 residual)
  rate 100% on the labelled scenario set (split, PO-won, discount+deduction,
  exact cases). Basis: synthetic seed scenarios, computed live per call.
- Delay model: MAE 3.42 days vs 25.78 days naive baseline; deduction validity
  AUC 0.846. Basis: synthetic generator with learnable signal, 80/20
  time-ordered holdout (960 train / 240 test rows).
- Test suite: 19 pytest tests + 4 Rust unit tests, all passing, repeatable.
North star (product): Touchless Cash Rate at $0 residual. These figures are
engineering verification on seed data, NOT customer results; no customer
metric may be quoted until a pilot produces it.

## 6. Non-goals (v1)
- Live ERP write-back (posting payloads are produced and labelled simulated;
  SAP/Oracle/NetSuite connectors are the v1.1 integration track).
- Bank feed ingestion (lockbox/BAI2/MT940 parsers are roadmap; CSV and API
  ingestion are live).
- Multi-instance shared metrics/rate-limit store (single-instance semantics
  documented; Redis path specified in ARCHITECTURE.md).

## 7. Risks and mitigations
- LLM hallucinated references -> verifier gate; parse never posts directly.
- Solver blow-up on huge candidate sets -> candidate restriction + solver
  time limits + exception routing (NP-hard core is bounded in practice).
- Policy misconfiguration -> policies are data, snapshotted per run, auditable.
- Data sensitivity -> keys hashed, per-tenant isolation, no key logging.
