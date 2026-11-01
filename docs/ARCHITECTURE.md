# AutoCash v2 - Architecture and System Design
Status: Production Release (Nov 2026). This document specifies the complete end-to-end architecture, mathematical formulations, and verification contracts running live in this repository.

## 1. Problem, from first principles
Cash application is a conservation problem with an information problem on top.
- Conservation: every cent received must be allocated to invoices, discounts, deductions or an explained residual. The ledger must balance exactly; "approximately matched" is a failed close.
- Information: the evidence for allocation arrives as unstructured, error-prone remittance text, often missing, sometimes wrong, across subsidiaries and currencies.
Therefore the system separates the two: probabilistic components (parsing, classification, prediction) may only propose; deterministic components (MILP solver, accounting rules, posting builder) dispose, and they must reconcile to the cent. Anything that cannot be reconciled becomes a tracked exception with an owner and a next action, never a silent write-off.

## 2. Components
- API (FastAPI, Python OOP): the only entry point. Routers per resource: ledgers, payments, runs, matches, exceptions, forecasts, evaluations, copilot, policies, transforms.
- Domain layer: dataclasses and invariants (Invoice, Payment, Match, Deduction, AgentRun, StepLog, Policy, Alias). Money is integer cents everywhere; floats never carry money.
- Repository layer: SQLite in v1 (single file, WAL mode), schema designed Postgres-compatible (no SQLite-only types in domain code). All writes through repositories; services never touch SQL directly.
- Agent framework (in-repo, no external agent library for the core loop):
  - Agent base class: name, input/output schema, run(ctx) returning StepResult with evidence and confidence.
  - Orchestrator: executes the pipeline as a DAG, persists a StepLog per step (input hash, output, latency, status), supports retry per step, resume from a failed step, and human approval gates (matches below the policy threshold and disputes above the policy value require approval before posting).
  - Idempotency: every run carries an idempotency key; re-submitting the same key returns the original run. Posting batches are idempotent per run.
- Job queue: batch reconciliation runs are enqueued (SQLite-backed queue in v1) and executed by a worker pool (asyncio, configurable concurrency). Jobs report progress via the API. The queue interface (enqueue, lease, complete, fail) is the same contract a Redis/SQS implementation would satisfy; agents do not know which implementation is behind it.
- Solvers:
  - MILP solver (scipy.optimize.milp): the original AutoCash formulation, productised - candidate restriction per payer/subsidiary, cash conservation equality, discount linking constraints, age-weighted objective, residual slacks with dominant penalty.
  - Subset-sum fast path (DP over cents with bounded candidate sets) used for candidate generation and for the counterfactual "why not this invoice" computation.
  - Greedy baseline: kept permanently, as the evaluation benchmark the MILP must beat.
  - Rust kernel (separate crate): pure functions for candidate generation and subset-sum, JSON bridge, Python fallback with identical semantics; equivalence enforced by shared fixtures in tests.
- ML services:
  - Training pipeline (scikit-learn): features from payment history (customer behaviour aggregates, amount, terms, seasonality). Models: payment-delay regression and deduction-validity classification. Offline evaluation on a time-ordered holdout; metrics stored per model version; inference only through a versioned ModelService. Models propose scores; policy converts scores to actions.
  - Anomaly service: z-score and IQR detectors over deduction history and payment amounts, plus deterministic rules (duplicate fingerprint, tolerance bands).
- AI (LLM) services - Gemini:
  - Remittance parser: schema-bound JSON extraction from raw text; a verifier reconciles extracted totals and references against deterministic checks; conflicts route to exceptions.
  - Column mapper: proposes mappings from arbitrary upload headers to the canonical schema; human corrections are stored per source fingerprint and reapplied automatically.
  - Reason classifier: proposes a deduction reason code with calibrated confidence display; below threshold, top-2 candidates go to the analyst.
  - Copilot: retrieval over the run's own records (no free-floating knowledge), answers with record citations, and can invoke product actions (run solver, filter exceptions, draft mail) only through typed tools with a confirmation step and an audit entry.
  - All LLM calls go through one client wrapper: key from server environment only, timeouts, retry with backoff, response schema validation, and a deterministic fallback path for every feature so the product remains fully functional with no key configured (degraded mode is surfaced in the UI and API health response, never hidden).
- Transform layer (LiveCube-style): ingestion normalises CSV/Excel/EDI-820-style/bank text into canonical tables; a cube API provides pivot, filter, group-by aggregations over invoices, payments and matches for the frontend grid and exports.
- Posting builder: from approved matches, builds journal lines and outbound payloads (JSON and EDI 820-style text), labelled with batch id and source run; reversal entries are generated, never edited in place.

## 3. Data model (core tables)
- customers(id, name, subsidiary, terms_days, behaviour aggregates cached)
- invoices(id, customer_id, invoice_number, po_number, gross_cents, currency, due_date, discount_rate, discount_terms, status)
- payments(id, payer_raw, payer_customer_id nullable, amount_cents, currency, received_date, channel, raw_remittance_text, fingerprint)
- remittances(id, payment_id, parsed_json, parser_version, verification_status)
- runs(id, idempotency_key, kind, status, policy_snapshot_json, started_at, finished_at)
- run_steps(id, run_id, agent_name, status, latency_ms, evidence_json, confidence)
- matches(id, run_id, payment_id, status proposed/approved/posted/rejected)
- match_lines(id, match_id, invoice_id, gross_cents, discount_cents, net_cents, factors_json)
- deductions(id, payment_id, claimed_cents, reason_raw, reason_code, z_score, validity_score, action, status)
- exceptions(id, run_id, kind, severity, owner, recommended_action, status, resolution_json)
- forecasts(id, horizon_days, payload_json, model_version, created_at)
- aliases(id, raw_name, customer_id, source run/override, created_at)
- audit_log(id, actor, action, entity, entity_id, payload_json, created_at)
- policies(id, name, weights_json, thresholds_json, active)
- models(id, kind, version, metrics_json, artifact_path, trained_at)

## 4. Policies (productised judgement)
A policy is data, not code: solver weights (age weight, discount penalty, residual penalty), automation threshold, auto-dispute minimum expected recovery, tolerance write-off ceiling, maker-checker value threshold. Every run snapshots the active policy so results are reproducible and auditable. Changing policy creates a new version; old runs keep theirs.

## 5. Failure semantics
- Solver infeasible/timeout: run completes as PARTIAL with residual explained per payment; never a 500.
- LLM unavailable or invalid output: parser falls back to deterministic extraction; the step is marked degraded with the reason in the StepLog.
- Worker crash mid-run: job lease expires, run resumes from the last completed step.
- Bad upload: row-level validation errors returned; valid rows ingest, invalid rows quarantine with reasons.

## 6. Security and controls
- No secrets in the repo; GEMINI_API_KEY and DB settings via environment. API keys never reach the frontend.
- Maker-checker: postings above the policy value threshold require a second approver role.
- Full audit log on approvals, overrides, alias learning, policy changes and postings.
- All demo/seed data is synthetic and labelled; the product ships with a seed generator, not with anyone's financial data.

## 7. Scaling path (design, honestly labelled)
Stateless API replicas behind the queue; ledger partitioning by subsidiary for solver candidate restriction (already the solver's first filter); solver time budget per payment with heuristic handoff (subset-sum fast path, then greedy with residual report) when candidate sets exceed the exact budget; model inference is in-process and cheap relative to solving. The v1 queue and DB are single-node implementations of the same contracts.
