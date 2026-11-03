# AutoCash - Architecture and System Design
AutoCash product pack, document 3 of 8. Previous: Market and Segment
Research. Next: Implementation Guide.
This document describes the system as it runs today. Where a capability
is a design for a later stage rather than built software, the text says
so in plain words and the section is labelled as design or roadmap.

## 1. First principles
Cash application is a conservation problem with an information problem
on top.

- Conservation: every cent received must be allocated to invoices,
  discounts, deductions or an explained residual. The ledger must
  balance exactly. Approximately matched is a failed close.
- Information: the evidence for the allocation arrives as unstructured,
  error-prone remittance text, often incomplete, sometimes wrong.

The architecture follows from that split. Probabilistic components
(parsing, classification, prediction) may only propose. Deterministic
components (the solver, accounting policy, the posting builder) decide,
and they must reconcile to the cent. Anything that cannot be reconciled
becomes a tracked exception with a recommended action, never a silent
write-off.

## 2. High-level system architecture
One container image. Inside it: a FastAPI application (Python), a
static frontend served by the same process, a compiled Rust kernel
binary, and the Tesseract OCR engine. State lives in SQLite databases
on a data directory: one database file per tenant, in WAL mode, plus
per-session workspace databases. There is no separate job server and no
external queue in this version; a reconciliation run executes inside
the request that starts it and records every step as it goes. That is
a deliberate trade: the run sizes this product targets complete in
seconds, and the audit trail is simpler when the record is written by
the code that did the work.

```text
+------------------------------------------------------------------+
| Presentation layer (frontend/)                                   |
| 14 views in 3 groups, served by the API process, no business     |
| logic of its own: every figure is fetched from the API           |
+------------------------------------------------------------------+
| API and isolation layer (backend/app/api.py)                     |
| REST under /api/v1, X-Workspace-Session workspace isolation,     |
| X-Tenant-Id tenancy, role-aware policy validation                |
+------------------------------------------------------------------+
| Six-agent execution layer (batch.py, solvers.py, rust_bridge.py) |
| Capture, Linking, Matching, Deduction, Policy, Briefing,         |
| executed in evidence order and recorded per run                  |
+------------------------------------------------------------------+
| Persistence and ERP layer (repository.py, erp_sap.py, mail.py)   |
| SQLite WAL per tenant, balanced BAPI_ACC_DOCUMENT_POST builder,  |
| outbox with honest recorded_not_sent states until SMTP is set    |
+------------------------------------------------------------------+
```

## 3. Workspaces, sessions and tenancy
A tenant holds the standing data: invoices, payments, policy, audit.
Two demo tenants ship in the product (demo, the US book, and demo-eu);
the tenant header is X-Tenant-Id. A workspace is one reviewer's
working copy of a tenant. Each browser session receives its own
workspace, identified by the X-Workspace-Session header carrying the
full session UUID, which the frontend attaches to every call, so two
people opening the same link never see or disturb each other's runs.
Session repositories are cached in memory with an LRU cap of 128.

Loading a case stages data into the workspace only; nothing executes
until the run is started. The workspace reports its own state (empty,
staged, executed) and every read model derives from it, which keeps
all screens in agreement about what has and has not run.

One boundary is stated honestly: switching tenant isolates data, runs
and policy completely, but it does not remap currency or the ERP chart
of accounts. Those are properties of the tenant's book, not of the
switcher.

## 4. The reconciliation pipeline
A run moves through six recorded agents, in order:

1. Capture: reads the staged payments, blocks exact duplicates before
   matching (a SHA-256 fingerprint of payer, amount and currency),
   and reports the staged totals.
2. Linking: resolves each payer to a customer (exact name, learned
   alias, or a stated fuzzy match) and restricts the candidate
   invoices.
3. Matching: solves each payment against its candidate invoices (see
   section 5) and records the derivation for every outcome.
4. Deduction: classifies claimed deductions, checks them against the
   customer's history, and values disputes.
5. Policy: applies the automation rules to each solved match: post
   it, hold it for a person (with the reason), or refuse it.
6. Briefing: composes the executive case brief and the settlement
   drafts from the run's final records.

Every step writes a run-step record with its status, its measured time
and its evidence, retrievable at GET /api/v1/runs/{run_id}/agents. The
agent strip on screen is rendered from those records, not from a
separate progress guess.

## 5. The matching engine

### 5.1 Formulation, in plain text
Money is integer cents everywhere; floats never carry money. For one
payment of P cents, the candidate pool is a set of open invoices of a
single customer in a single currency. For each candidate invoice i:

```text
gross_i      = open balance of invoice i, in cents
discount_i   = the early-payment discount available on invoice i, in cents
x_i          = 1 if invoice i is selected, else 0
y_i          = 1 if the discount on invoice i is taken, else 0
take_claim   = 1 if the payment's claimed deduction is accepted, else 0
s_plus       = unexplained remainder in one direction, in cents (0 or more)
s_minus      = unexplained remainder in the other direction, in cents (0 or more)

Cash conservation (an equality, never an approximation):
  sum over i of (gross_i x x_i - discount_i x y_i)
      - claimed deduction x take_claim + s_plus - s_minus = P

A discount can only be taken on an invoice that is selected:
  y_i is at most x_i, for every i

Objective (minimise):
  - (1 + age_days_i x 0.05) for each selected invoice
      (a reward for selecting, stronger for older invoices: FIFO pressure)
  + 50 if a discount is taken on an invoice
  + 10 if the claimed deduction is accepted
  + 1,000,000 x |residual| in cents
      (dominant: unexplained cash is the enemy)
```

The solver is mixed-integer linear programming (scipy.optimize.milp,
HiGHS) under that equality, with a hard time limit on every call. A greedy first-fit matcher is kept
permanently as the benchmark the solver must beat; the evaluations
endpoint runs both over labelled cases and reports the comparison,
and the product's benchmark claims come only from that comparison.

### 5.2 Candidate restriction and hard boundaries
Before any solving, each payment's candidate invoices are narrowed in
a cascade (stated references first, then purchase-order numbers, then
the payer's own open invoices, then the full ledger as a last resort).
This bounds the hard part of the problem in practice. Two boundaries
are hard, not preferences: a candidate must share the payment's
currency, and a payment can only ever clear one customer's invoices
(a whole-ledger search is solved per customer and the best
single-customer answer is taken).

### 5.3 Processing order is evidence order
A batch is solved in evidence order, never in the order the wires
happen to sit in the file. Each payment carries an evidence rung, and
the run sorts by it before solving:

| Rung | Evidence | Meaning |
| :--- | :--- | :--- |
| 0 | reference, po | The wire names its invoices, or its purchase order |
| 1 | ocr_reference | The reference was recovered by OCR repair |
| 2 | amount_payer, customer_ledger | Payer and amount point at the customer's ledger |
| 3 | fuzzy_payer | The payer matched by fuzzy name evidence |
| 4 | all_ledger | Nothing but a whole-ledger search |
| 5 | none | No usable evidence |

An unreferenced wire can therefore never consume an invoice that a
referenced wire in the same batch was sent to pay. The order used is
recorded in the Matching Agent's evidence for every run.

### 5.4 Ambiguity and evidence rules
An exact set is not automatically a confident one. If several distinct
invoice sets sum exactly to a wire that names none of them, the result
is a proposal for a person (status PROPOSED) with confidence capped at
0.75, never a posting. Matches reached on weak evidence carry their
own caps: fuzzy_payer and all_ledger matches are capped at 0.78
confidence, below the auto-post threshold. A match the policy accepts
posts; a match it questions holds with the reason stated.

### 5.5 Solver integrity guard
Solver tolerances can accept a set that is a few cents short at
seven-figure amounts; this was observed in testing, not hypothesised.
The engine therefore re-verifies every returned set in exact integer
arithmetic. A set that does not reconcile is cut from the problem and
the solver retries, at most 6 attempts, before returning an honest
no-match with a verification note. This guard has its own regression
test.

### 5.6 The Rust kernel, in its exact role
The subset-sum step also exists as a small Rust program. It is a
compiled binary, invoked over stdio with a JSON payload; it is not a
shared library and nothing loads it through FFI. Its role is precise:
on plain payments (no discounts, no claimed deduction) it attempts the
exact set first, and it decides the payment only when that set is
provably the unique exact set. Ties, discounts, deductions and
residuals are judged by the MILP. The kernel is proven equivalent to
the Python implementation on a 203-case generated suite, and the
diagnostics endpoint re-probes that equivalence live on every check.
Its path is configured by AUTOCASH_KERNEL_BIN.

### 5.7 Idempotency, settlement and partial payments
A run is idempotent by construction: only pending payments are solved,
payments that already carry a match or exception record in the
workspace are never solved twice, and re-executing a run returns the
standing run. An auto-posted match settles its invoices immediately,
so no later run can allocate them again.

Settlement on approval follows the money. Approving a fully covered
match settles its invoices. Approving a PARTIAL payment does not: the
applied amount is attributed across the lines (pro-rata, with the last
line taking the rounding remainder), each invoice stays open with its
gross reduced by what was actually applied, and the approval record
carries the partial_application detail, so the unpaid remainder
survives as a live receivable in the ledger, the forecast and future
candidate pools. An overpayment settles its invoices in full; the
excess is the customer's on-account credit.

### 5.8 Unearned discounts
When a solution takes an early payment discount on an invoice whose
discount window had already closed (the invoice is past its due date),
the discount is not treated as earned. It is recorded on the match
and, where the payment carries no claim of its own, claimed back
through the deduction machinery as reason code RC-12 (Unearned
Discount), with the same expected-value decision as any other claim.
Where a claim already exists, the unearned amount attaches to it.

### 5.9 Counterfactuals
For any invoice not chosen, the engine derives why not (amount, age,
discount and residual arithmetic), available on demand as the why-not
explanation. Outcomes are therefore never bare: an exact or
policy-clean solution posts or holds per policy; a partial solution
holds with its residual; an unsolvable payment becomes a reasoned
refusal with zero posting lines.

## 6. Confidence scoring and governance
Confidence is computed from evidence provenance and mathematical
precision, never from a zero residual alone. The governance rules live
in tenant policy, are validated on write, and are snapshotted into
every run. Defaults:

| Policy field | Default | Meaning |
| :--- | :--- | :--- |
| automation_threshold | 0.90 | Confidence at or above which a match may auto-post |
| maker_checker_threshold_cents | $100,000 | Value above which a second person must approve |
| tolerance_writeoff_cents | $25 | Variances at or below this are written off, not disputed |
| dispute_processing_cost_usd | $45 | Cost of pursuing a dispute, charged against expected recovery |
| auto_dispute_min_recovery_usd | $100 | Minimum expected recovery for an automatic dispute |
| residual_penalty | 1,000,000 | Solver objective weight on unexplained cents |
| discount_penalty | 50 | Solver objective weight on taking a discount |
| deduction_penalty | 10 | Solver objective weight on accepting a claimed deduction |
| age_weight | 0.05 | Solver objective FIFO pressure toward older invoices |

The built-in demo case discloses one deliberate deviation in its
policy_note: its maker-checker threshold is set to $60,000 so that two
of its payments demonstrate the hold. The product default is $100,000
and the deviation is printed, not hidden.

Decisions are atomic compare-and-set transitions: two approvers acting
on the same match at the same moment cannot both succeed; the second
receives a conflict. Approvals also teach the workspace: a confirmed
payer-to-customer link is stored as a learned alias for later runs.

## 7. Deduction intelligence
A claimed deduction is classified into a reason-code taxonomy by
keyword evidence, with the candidates and confidence recorded:

| Code | Meaning |
| :--- | :--- |
| RC-02 | Damaged/Shortage Claim |
| RC-05 | Pricing Discrepancy |
| RC-07 | Promotional Allowance |
| RC-09 | Freight Claim |
| RC-11 | Tax Withholding |
| RC-12 | Unearned Discount |
| RC-99 | Other/Unclassified |

The claimed amount is compared with the customer's claim history using
a z-score; a spike above 2.5 is flagged anomalous. History is computed
from the workspace's own stored matches, and it needs at least 3
samples per customer; below that, a labelled baseline prior (100000 /
40000) is used and the evidence says so.

The dispute decision uses an expected-value rule:

```text
expected recovery = win probability x claimed amount - $45 processing cost
```

The win probability is a transparent heuristic: 0.94 when proof of
delivery is verified clean, 0.35 otherwise. It is labelled as a
heuristic in the data, on screen and in every document the system
composes; it is not a trained model. An automatic dispute is raised
only when proof of delivery is clean and the expected recovery exceeds
$100. Small amounts inside the $25 tolerance are written off by
policy. Nothing about this chain is hidden inside a model.

## 8. AI services, and their limits
One client wrapper carries every AI call: the key comes from the
server environment only (GEMINI_API_KEY), the model name is read from
the environment (GEMINI_MODEL) so operations can change it without a
code change, the client timeout (GEMINI_TIMEOUT_S, default 40 seconds)
sits below the hosting platform's request ceiling, and output length
is capped. Gemini is live in the reference deployment, running
gemini-3.5-flash-lite; a live probe of the parse route returned
source=gemini in about 3.2 seconds.

- Remittance parsing: Gemini returns schema-bound JSON for payer,
  amount, references and deductions (POST /api/v1/parse). A
  deterministic verifier then checks the result: totals must
  reconcile with the extracted fields, and every invoice or PO
  reference must exist in the open ledger. Invented references are
  flagged by name. If the AI call fails, times out, is rate limited
  or fails verification, a deterministic parser (patterns and rules,
  no AI) produces the extraction instead, and the response states
  which source produced it. The fallback is labelled deterministic,
  never presented as AI. The health endpoint reports the AI mode and
  the last AI error at all times.
- File intake: uploads arrive as PDF (text layer), PNG or JPG (OCR),
  plain text or email files, through POST /api/v1/import/file with a
  JSON body carrying base64 content. Extraction feeds the same
  verifier.
- Draft composition: dispute, inquiry and reminder texts are composed
  from the record, by the AI when available (POST /api/v1/ai/draft)
  and by grounded templates otherwise. Dispute tones are strict,
  contract and escalate. The reviewer always sees which source wrote
  a draft.
- The assistant (POST /api/v1/copilot): answers are built from the
  product's own records (matches, exceptions, forecast, the live
  approvals queue), with citations to those records, and questions
  outside the records are refused plainly. It reads live state, so an
  answer about the queue reflects decisions already taken. It cannot
  post, approve or send anything.

## 9. Forecast and collections
The forecast consumes only the residual ledger: the invoices still
open after the latest run, at their post-reconciliation balances,
with settled invoices removed by the same records the run produced.
It projects eight weeks, runs a Monte Carlo simulation (400
simulations) for P10, P50 and P90 bands, and accepts what-if changes
(POST /api/v1/forecast/whatif) against the same position. Collections
priorities and dunning segments (GET /api/v1/collections) derive from
the same residual set, so the forecast, the ledger and the mail hub
cannot quietly disagree.

The payment-delay model behind the forecast is stated with its basis:
mean absolute error 2.948 days against a 7.665-day naive baseline, and
a deduction-validity AUC of 0.846, trained on a disclosed synthetic
generator (1,200 rows, 960 training and 240 held out, six customer
profiles with learnable delay signal). Each invoice is predicted from
its own facts: its amount, its own payment terms derived from its age
and due days (clamped to the 15 to 60 day range the model was
validated on), and the real current calendar month. A customer the
model has never seen is scored with no customer-specific component,
never with another customer's behaviour borrowed under its name. A
partially paid invoice forecasts at its remaining balance, and the
ledger shows the partial application (amount applied against the
original invoice total) on the invoice's own row. Retraining on real
payment history is the model v2 roadmap item (see section 16).

## 10. The SAP posting pack
For every cleared payment, the posting builder creates a DZ clearing
document whose journal lines come from the match's own derivation
equation. Because the inputs already reconcile, debits equal credits
by construction, and the builder asserts the balance on every
document. The chart of accounts, exactly as the code holds it:

| GL | Account | Role in the journal |
| :--- | :--- | :--- |
| 113100 | Cash - operating account | Debit: the payment received |
| 121000 | Trade receivables - customer control | Credit: the gross cleared against invoices |
| 121500 | Disputed receivables - deduction claims | Debit: disputed amounts reclassified for recovery |
| 121600 | Residual receivable - part-paid invoices | Debit: an underpayment's unpaid remainder |
| 121900 | Unapplied cash - customer on-account | Credit: an overpayment's excess, held as the customer's credit |
| 119900 | Unapplied cash suspense | Only for wires that match nothing at all, when parked |
| 415000 | Sales discounts allowed | Debit: earned discounts taken |
| 529000 | Deductions accepted (within policy) | Debit: deductions accepted under policy |

The balancing line follows the residual's direction: an underpayment's
remainder posts to residual receivable (the customer still owes it,
and it stays visible), an overpayment's excess posts to on-account
credit. Neither is parked in generic suspense; suspense is reserved
for wires that match nothing at all. Disputed deductions produce a
separate reserve journal that reclassifies the claimed amount to
disputed receivables (ASC 606 / IFRS 15), leaving revenue untouched.

Document numbers are deterministic. A cleared auto-posted match takes
DZ-1400 followed by 6 digits derived from the SHA-256 of its match ID.
An approved match carries the document ID issued at approval: DZ-
followed by the first 10 characters of its SHA-256 fingerprint. Every
cleared document's status is STAGED_FOR_SAP_POSTING; held matches keep
preview semantics with no document number until they clear. Each
document carries the full BAPI_ACC_DOCUMENT_POST payload (JSON) in the
shape an S/4HANA system expects, with the resolved customer on every
receivable line. The run's documents are listed at GET
/api/v1/erp/run-documents; a single payment's document is at GET
/api/v1/payments/{payment_id}/erp-document.

Approving a refusal creates no document at all: it records
PARKED_SUSPENSE with the amount in suspense GL 119900 and an audit
entry. The pack is produced for review; writing it into a live ERP is
the connector track, stated as such in the PRD.

## 11. Mail and the outbox
Every send intent is written to a per-tenant outbox with its kind, its
reference and its text. The Mail Hub (GET /api/v1/mail/hub) groups four
streams: dispute claims, unidentified-wire chases, settlement
confirmations and dunning reminders. Until SMTP credentials are
configured (AUTOCASH_SMTP_HOST, AUTOCASH_SMTP_PORT, AUTOCASH_SMTP_USER,
AUTOCASH_SMTP_PASSWORD, AUTOCASH_MAIL_FROM, AUTOCASH_SMTP_TLS), a send
is recorded with the status recorded_not_sent and the reason stored
with the record and shown to the reviewer. The status sent is used
only when a mail server has accepted the message. All sends, in either
state, are audit events.

## 12. Enterprise controls
- Tenancy: one SQLite database per tenant, opened in WAL mode with a
  5000 ms busy timeout; nothing crosses tenants.
- Authentication: API keys are SHA-256 hashed at rest and shown once
  at issuance. Roles: viewer, analyst, approver, admin. When no
  bootstrap key (AUTOCASH_BOOTSTRAP_KEY) is configured, the deployment
  runs in an explicitly labelled demo-open posture (GET /health prints
  auth: dev-open); secured mode is the same build with the key set.
- Approvals: maker-checker is policy, not code. The threshold lives in
  the tenant's policy, is snapshotted into every run, and a decision
  on a held match (POST /api/v1/matches/{match_id}/decision) settles
  invoices in full, or to the extent paid for a partial payment,
  issues the posting document and writes an audit entry.
- Audit: decision and send entries carry a SHA-256 content fingerprint
  that lets anyone recompute and verify the entry later (GET
  /api/v1/audit).
- Limits and observability: per-key rate limiting (300 requests per
  minute by default, AUTOCASH_RATE_LIMIT_PER_MIN), a request ID on
  every call, structured JSON logs, Prometheus metrics at GET
  /metrics, a readiness check at GET /ready, and a diagnostics
  endpoint (GET /api/v1/diagnostics) that reports dependency state,
  the live Rust kernel equivalence probe and the AI mode and last
  error. The diagnostics response redacts the mail password.
- Export: the audit and SAP bundle is refused with a clear conflict
  response until a run exists, because an export with nothing behind
  it would be a hollow artefact.

## 13. Frontend
A static single page (fourteen screens) served by the API process, in
four classic scripts (state, operate, insight, assist) over one
stylesheet; there are no ES modules and no build step. It holds no
business logic of its own: every figure is fetched from the API
through one helper that attaches the workspace session header, and
asset URLs carry version stamps so a new deployment is never masked
by a browser cache. Interface state that must survive navigation
(brief open or closed, mail category, draft sequence) is kept in the
page session and guarded by sequence counters, so a slow response can
never overwrite a newer screen. Interactive values are passed to
handlers through data attributes, never interpolated into handler
strings; a contract test scans the shipped scripts for the unsafe
pattern and asserts zero occurrences.

## 14. Build and release
The test suite (134 automated tests across 29 modules, plus the 4
Rust kernel tests) gates the container build in continuous
integration: a failing suite means no image. The image is built from
the repository's Dockerfile in two stages (rust:1.82-slim compiles the
kernel, then python:3.12-slim carries the application with the kernel
binary and the OCR engine placed inside), serves on port 8080, and
answers its healthcheck at /ready. Deployment is a service update on
the hosting platform; there is no in-place mutation of a running
version. The full release flow is the AWS Deployment Runbook
(document 6).

## 15. Failure semantics, as built
- Solver cannot solve a payment: the run completes, that payment is a
  refusal or an exception with its reason, and the run summary counts
  it. Never a server error.
- AI unavailable at any point: the deterministic path answers, the
  mode is labelled, and the error is visible on the health endpoint.
- A duplicate payment: stopped before matching, recorded as an
  exception, and never double-posted. Re-running a batch returns the
  standing run rather than a second set of matches.
- An approval on a refusal: parks the amount in suspense with an
  audit entry and no posting document.
- Data on the demonstration host is ephemeral by design (see the
  Deployment Guide); a case reload restores the full demonstration in
  one action.

## 16. Scaling path and roadmap (design, honestly labelled)
The following are designs, not built software: stateless API replicas
behind a shared queue and a shared rate-limit and metrics store
(Redis-class); tenant databases migrated to Postgres (the schema
avoids SQLite-only types in domain code for this reason); solver time
budgets per payment with a documented heuristic handoff for very large
candidate sets. The single-instance version is exact about its own
limits in the Implementation Guide.

Roadmap items, named as such in the PRD: model v2, whose delay and
validity features include the customer's actual workspace payment and
deduction history; and Save & Retrieve by Session ID, for named,
restorable workspaces beyond the current per-session isolation.

Version 3.0 | 3 Nov 2026 | Owner: C. Harsha Vardhana Reddy
