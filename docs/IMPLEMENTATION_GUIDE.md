# AutoCash - Implementation Guide
AutoCash product pack, document 4 of 8. Previous: Architecture and
System Design. Next: Deployment Guide.
For a customer finance and IT team piloting AutoCash. Estimated pilot
effort: one to two weeks part-time, dominated by data extraction, not
software setup.

## 1. Deploy the service
Option A - Docker (recommended). One image contains the application,
the Rust kernel and the OCR engine:
  docker build -t autocash .
  docker run -p 8080:8080 -v autocash-data:/app/data \
    -e AUTOCASH_BOOTSTRAP_KEY=<strong secret> \
    -e GEMINI_API_KEY=<optional, enables AI parsing> \
    -e GEMINI_MODEL=gemini-3.5-flash-lite autocash
Option B - AWS ECS: the reference production deployment is documented
step by step in the AWS Deployment Runbook (document 6 of this pack).
Option C - Local evaluation: Python 3.12, a virtual environment,
pip install -r backend/requirements.txt, then run
uvicorn api:app --app-dir backend/app.

Two configuration points matter. First, set GEMINI_MODEL explicitly:
if it is absent, the application falls back to a built-in default that
may not suit your account, and the failure mode is a slow answer rather
than a clear error. The reference deployment uses
gemini-3.5-flash-lite. Second, decide the posture. With a bootstrap key
set, the service is secured and every call needs a tenant API key.
Without one, it runs in a demo-open posture that the health endpoint
labels as such (auth: dev-open); use that only for demonstrations on
synthetic data.

## 2. Module-by-module code map

### Backend modules (backend/app/)
| Module | Role |
| :--- | :--- |
| api.py | Every FastAPI route, the auth context, tenant and workspace-session resolution, rate limiting, diagnostics |
| batch.py | The six-agent run: evidence-order processing, duplicate blocking, idempotent re-execution, settlement on auto-post |
| solvers.py | The MILP solver (HiGHS) and the greedy baseline; exact integer re-verification of every returned set, with cuts and bounded retries |
| rust_bridge.py | Invokes the Rust kernel binary over stdio with a JSON payload; decides only provably-unique exact sets on plain payments |
| domain.py | Core data types and the policy object: thresholds, tolerances and solver objective weights, with range validation |
| repository.py | SQLite storage, one database per tenant (WAL, busy timeout), matches, approvals with compare-and-set decisions, audit entries with content fingerprints |
| tenants.py | Tenant registry and API key issuance; keys are SHA-256 hashed at rest and shown once |
| reference_engine.py | The deterministic remittance engine: pattern-based extraction and the ledger verifier applied to every parse, AI or not |
| ingestion.py | CSV and file intake: column synonym mapping, locale number parsing, discount validation, quarantine of invalid rows |
| ai.py | The Gemini client wrapper: environment-only key and model, client timeout below the platform ceiling, capped output, source labelling |
| anomaly.py | Deduction intelligence: the RC reason-code taxonomy, z-score anomaly checks against customer history, expected-recovery valuation |
| erp_sap.py | The SAP posting pack: balanced DZ journals and the BAPI_ACC_DOCUMENT_POST payload builder |
| forecast.py, ml.py | The payment-delay model and the Monte Carlo forecast over the post-reconciliation residual ledger |
| briefing.py | The executive case brief and the mail draft composition, including dispute tones |
| copilot.py | The grounded assistant: answers from the product's own records, read from live state |
| mail.py | The outbox and SMTP sending, with recorded_not_sent states until a mailbox is configured |
| fuzzy.py | Payer-name fuzzy matching and learned payer-to-customer aliases |
| scenarios.py | The ten scenario packs and their checks, run through the real pipeline |
| seed.py | The built-in demo case: 19 invoices, 16 payments, one realistic day of receipts |
| methodology.py | The definitions the product prints next to its figures, including the autonomous-resolution definition |

### Frontend files (frontend/)
| File | Role |
| :--- | :--- |
| index.html | The fourteen screens' markup in three groups; asset URLs carry version stamps |
| css/livecube.css | The design system: dark panels, zero-radius surfaces, Inter Tight, Inter and JetBrains Mono |
| js/state.js | Workspace session identity, the single api() helper that attaches session headers, navigation and lazy per-view loading |
| js/operate.js | Dashboard, Use Cases, Upload Center, and the Run Reconciliation pipeline: the agent strip, the staged box, matches and why-not explanations |
| js/insight.js | Ledger, Forecast and Collections, Evaluations, Agent Health and diagnostics, the SAP document viewer, and this document pack's viewer |
| js/assist.js | Policy Studio, Methodology, the approvals queue, the Mail Hub and outbox, the executive case brief, and the copilot panel |

The frontend is classic scripts, not ES modules, and there is no build
step. Interactive values reach handlers through data attributes, never
through interpolated strings; a contract test enforces that.

## 3. Key API contracts
All routes are under /api/v1 unless shown otherwise. Session calls
carry X-Workspace-Session; tenant calls carry X-Tenant-Id.

| Method and path | Purpose | Key behaviour and guarantees |
| :--- | :--- | :--- |
| GET /health | Liveness, posture and model metrics | Prints auth: dev-open when no bootstrap key is set; reports the AI mode and last AI error |
| GET /ready | Readiness check | The container healthcheck target |
| GET /metrics | Prometheus metrics | Per-path request counters |
| POST /api/v1/seed | Stage the lightweight seed set | Used by API-level batch flows and tests |
| GET /api/v1/workspace | Read the workspace snapshot | Reports the workspace state (empty, staged, executed) and its staged totals |
| POST /api/v1/cases/{cid}/load | Stage a case (demo id: seed) | Stages invoices and payments; executes nothing |
| POST /api/v1/workspace/run | Execute reconciliation | Pending payments only; re-execution returns the standing run instead of posting twice |
| POST /api/v1/workspace/reset | Clear the workspace | Returns the session to the empty state |
| POST /api/v1/batches | Run a submitted batch of payments | Idempotency-keyed; a repeated key returns the original run |
| GET /api/v1/approvals | The maker-checker queue | Current PROPOSED matches, newest first, including the zero-line refusal by design |
| POST /api/v1/matches/{match_id}/decision | Approve or reject a held match | Body: {decision: approve or reject}. Atomic compare-and-set; a second concurrent decision gets a conflict. Approving the zero-line refusal records PARKED_SUSPENSE and creates no posting |
| GET /api/v1/invoices | The open invoice book | Carries partial-application detail on part-paid invoices |
| PATCH /api/v1/invoices/{invoice_id} | Edit an open invoice | Withdraws any affected PROPOSED match |
| PATCH /api/v1/payments/{payment_id} | Edit a staged payment | Withdraws any affected PROPOSED match |
| POST /api/v1/import/file | Import a remittance file | JSON body with base64 content; PDF text layer, PNG/JPG via OCR, plain text and email files |
| POST /api/v1/parse | Parse remittance text | Response states its source (gemini or the deterministic parser), whether it degraded, and the verifier's findings |
| GET /api/v1/runs/{run_id}/agents | Per-agent run evidence | Status, measured time and evidence per agent, including the processing order used |
| GET /api/v1/payments/{payment_id}/erp-document | One payment's posting document | Balanced DZ journal and BAPI payload for a cleared payment |
| GET /api/v1/erp/run-documents | The run's posting pack | Every cleared document with run totals; balanced by construction |
| GET /api/v1/forecast | Cash forecast | Computed only from the post-reconciliation residual ledger; 8 weeks, P10/P50/P90 |
| POST /api/v1/forecast/whatif | What-if against the forecast position | Applies a hypothetical receipt or settlement to the same residual position |
| GET /api/v1/collections | Collections priorities | Derived from the same residual set as the forecast |
| GET /api/v1/mail/hub | The outbound mail hub | Disputes, chases, settlements and dunning, composed from run records |
| POST /api/v1/mail/send | Send or record a composed mail | Records recorded_not_sent with the reason until SMTP is configured; sent only on SMTP acceptance |
| POST /api/v1/ai/draft | Compose a dispute, chase or reminder draft | AI when available, grounded templates otherwise; the source is stated |
| POST /api/v1/copilot | Ask the grounded assistant | Answers from product records with citations; reads the live approvals queue |
| POST /api/v1/why-not | Counterfactual for one invoice | The arithmetic of why a given invoice was not chosen for a payment |
| GET /api/v1/evaluations | Solver benchmark | MILP accuracy against greedy on the labelled ground-truth cases, computed per call |
| GET /api/v1/scenarios | List the scenario packs | The ten packs and what each one exercises |
| POST /api/v1/scenarios/{sid}/run | Run one scenario pack | Executes through the real pipeline and returns its checks |
| GET /api/v1/docs, GET /api/v1/docs/{name} | This document pack | Served in flow order, PRD first |
| GET /api/v1/diagnostics | Dependency and subsystem state | Kernel equivalence probe, AI state, mail state with the password redacted |
| GET /api/v1/audit | The audit trail | Decision entries carry SHA-256 content fingerprints |

There is deliberately no approve-my-match shortcut and no park
endpoint: approvals are decisions on matches (above), and parking is
what approving a refusal records.

## 4. First-run setup (about 15 minutes)
1. Create the tenant: POST /admin/tenants with the bootstrap key.
   The response carries the tenant_id.
2. Issue keys: POST /admin/tenants/{tenant_id}/keys, one per role
   (admin, approver, analyst, viewer). Each key is shown once. Store
   them in your secrets manager; only their hashes are kept.
3. Set policy: PUT /api/v1/policy with your thresholds: the automation
   confidence threshold, the tolerance write-off ceiling, the
   maker-checker value above which a second person must approve, and
   the minimum expected recovery for an automatic dispute. Values are
   range-validated; invalid values are rejected with a 422.
4. Verify: GET /health should report the secured posture, and
   GET /ready should be green.

## 5. Data onboarding
- Open invoices: import CSV through the Upload Center, or stage a case
  through the API. Common column synonyms are recognised
  automatically. Rows that cannot be mapped or validated are returned
  as quarantined errors with row numbers; nothing is silently dropped.
  Amounts are parsed with locale awareness, negative or zero amounts
  are quarantined, and the discount column is read as a percentage.
  Every import carries a content fingerprint for audit.
- Payments: stage them through the Upload Center, the case loader or
  the batch API. Bank and lockbox file adapters are configured per
  customer during the pilot; they are not part of the standard build,
  and this guide does not pretend otherwise.
- Remittance files: PDF, PNG, JPG, plain text and email files can be
  uploaded for extraction. The extracted fields are verified against
  the open ledger before anything is staged.
- Customer aliases: payer name variants are stored per tenant as
  analysts confirm matches, and are applied to later runs.

## 6. How a pilot team works day to day
Each reviewer works in their own browser-session workspace, so parallel
review never collides. The rhythm is: load a case or the day's receipts
(staging changes nothing), execute the run, work the approvals queue,
review the SAP posting pack, and let the mail hub compose the dispute
claims, inquiries and confirmations from the run. The forecast and
collections views update from the residual ledger the run leaves
behind. At any point, the audit and SAP bundle can be exported for
review; the export is refused until a run exists, by design.

## 7. Verification and the automated test suite
The backend/tests directory holds 134 automated tests across 29 pytest
modules, plus 4 Rust kernel tests (cargo test). The suite runs in CI
and gates the container build: a failing suite means no image.

```bash
python -m pytest backend/tests -q
cargo test --manifest-path rust-kernel/Cargo.toml
```

Suites a reviewer will care about most:

- test_audit_remediation.py: the regression tests named after the
  defects the audit rounds found: idempotent re-runs, cross-customer
  and currency boundaries, ambiguous ties, atomic decisions, partial
  settlement, document balance for partial and overpaid matches.
- test_erp_documents.py and test_refusal_parking.py: every generated
  SAP document balances with a named customer; approving a refusal
  parks in suspense and posts nothing.
- test_milp_solvers.py and test_rust_equivalence.py: solver behaviour,
  and the 203-case equivalence suite between the kernel and Python.
- test_core_pipeline.py: all ten scenario packs pass through the real
  run path.
- test_ui_contracts.py: the page structure, the asset version stamps,
  and the ban on interpolated inline handlers.

## 8. Go-live checklist
- [ ] Policy thresholds signed off by the AR manager, maker-checker
      value set deliberately, not left at the default
- [ ] Pilot scope fixed: one subsidiary, one bank account, two weeks
      of payments
- [ ] Baseline measured before the pilot: current manual match rate
      and analyst hours, so the result can be compared honestly
- [ ] Approvals queue ownership assigned, with a daily review cadence
- [ ] Gemini configured, or deterministic mode accepted in writing
      (the product works fully without the AI; parsing quality, not
      function, is what changes)
- [ ] Mail posture understood: until SMTP is configured, sends are
      recorded as recorded_not_sent; connect the mailbox before any
      live sending
- [ ] Success criteria agreed in advance: touchless rate, residual
      dollars, exception ageing, measured from AutoCash run records
      and exported for review

## 9. Operations
- Logs: structured JSON per request, each with a request ID. Ship them
  to your aggregator.
- Metrics: GET /metrics in Prometheus format. Alert on the 5xx rate.
- Readiness and diagnosis: GET /ready for the readiness check, and the
  diagnostics endpoint (Agent Health screen) for dependency state,
  including the Rust kernel equivalence probe and the current AI mode
  and last AI error.
- Backups: back up the data directory (one SQLite file per tenant, one
  per workspace session, plus the control database). Restore means
  replacing the files and restarting.
- Rate limits: AUTOCASH_RATE_LIMIT_PER_MIN per API key, default 300.
  The limiter is in-memory, which is exact for a single-instance
  deployment; multi-instance limiting is part of the scaling design in
  the Architecture document and is labelled there as design.
- Updates: ship a new container image and update the service. Tenant
  data on a persistent volume survives; on an ephemeral demonstration
  host it resets, and the demo case reloads in one action.

## 10. Security notes
- API keys are SHA-256 hashed at rest; raw keys exist only at issuance.
- Tenant isolation is physical: a separate database file per tenant.
- No payment data leaves the deployment except the optional Gemini
  parsing calls. Leave GEMINI_API_KEY unset and no external AI call is
  made at all; parsing falls back to the deterministic parser and says
  so in its response.
- The audit log records actor, action and payload for approvals,
  decisions, policy changes and sends, and decision entries carry a
  content fingerprint that can be recomputed to prove they were not
  altered.

Version 3.0 | 3 Nov 2026 | Owner: C. Harsha Vardhana Reddy
