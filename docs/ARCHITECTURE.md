# AutoCash - Architecture and System Design
AutoCash product pack, document 3 of 8. Previous: Market and Segment
Research. Next: Implementation Guide.
Version 2.0 | 2 Nov 2026. This document describes the system as it runs
today. Where a capability is a design for a later stage rather than built
software, the text says so in plain words.

## 1. First principles
Cash application is a conservation problem with an information problem on
top.

- Conservation: every cent received must be allocated to invoices,
  discounts, deductions or an explained residual. The ledger must balance
  exactly. Approximately matched is a failed close.
- Information: the evidence for the allocation arrives as unstructured,
  error-prone remittance text, often incomplete, sometimes wrong.

The architecture follows from that split. Probabilistic components
(parsing, classification, prediction) may only propose. Deterministic
components (the solver, accounting policy, the posting builder) decide,
and they must reconcile to the cent. Anything that cannot be reconciled
becomes a tracked exception with a recommended action, never a silent
write-off.

## 2. Shape of the system
One container image. Inside it: a FastAPI application (Python, object
oriented), a static frontend served by the same process, a compiled Rust
kernel binary, and the Tesseract OCR engine. State lives in SQLite
databases on a data directory: one database file per tenant, in WAL mode,
plus per-session workspace databases. There is no separate job server and
no external queue in this version; a reconciliation run executes inside
the request that starts it and records every step as it goes. That is a
deliberate trade: the run sizes this product targets complete in seconds,
and the audit trail is simpler when the record is written by the code
that did the work.

## 3. Workspaces and sessions
A tenant holds the standing data: invoices, payments, policy, audit. A
workspace is one reviewer's working copy. Each browser session receives
its own workspace, identified by a session header the frontend attaches
to every call, so two people opening the same link never see or disturb
each other's runs. Loading a case stages data into the workspace only;
nothing executes until the run is started. The workspace reports its own
state (empty, staged, executed) and every read model derives from it,
which keeps all screens in agreement about what has and has not run.

## 4. The reconciliation pipeline
A run moves through six recorded agents, in order:

1. Capture: reads the staged payments, blocks exact duplicates before
   matching (a fingerprint of payer, amount and currency), and reports
   the staged totals.
2. Linking: resolves each payer to a customer (exact name, learned alias,
   or a stated fuzzy match) and restricts the candidate invoices.
3. Matching: solves each payment against its candidate invoices (see
   section 5) and records the derivation for every outcome.
4. Deduction: classifies claimed deductions, checks them against the
   customer's history, and values disputes.
5. Policy: applies the automation rules to each solved match: post it,
   hold it for a person (with the reason), or refuse it.
6. Briefing: composes the executive case brief and the settlement drafts
   from the run's final records.

Every step writes a run-step record with its status, its measured time
and its evidence. The agent strip on screen is rendered from those
records, not from a separate progress guess.

## 5. The matching engine
Money is integer cents everywhere; floats never carry money.

- Candidate restriction: before any solving, each payment's candidate
  invoices are narrowed in a cascade (stated references first, then
  purchase-order numbers, then the payer's own open invoices, then the
  full ledger as a last resort). This bounds the hard part of the
  problem in practice. Two boundaries are hard, not preferences: a
  candidate must share the payment's currency, and a payment can only
  ever clear one customer's invoices (a whole-ledger search is solved
  per customer and the best single-customer answer is taken).
- Solver: mixed-integer linear programming (scipy.optimize.milp, HiGHS,
  sparse constraints, a hard time limit on every call) under a cash
  conservation equality: the sum of chosen invoice nets, discounts and
  explained deductions must equal the payment, with any residual
  carried as an explicit, heavily penalised term. The objective
  prefers exact sets, then older invoices, then fewer unexplained
  cents. On plain payments (no discounts, no claimed deduction) the
  Rust subset-sum kernel attempts the exact set first and decides the
  payment only when that set is provably the unique exact set; ties,
  discounts, deductions and residuals are judged by the MILP. The
  kernel binary is invoked over stdio with a JSON payload; it is never
  trusted without the uniqueness re-count.
- Ambiguity and evidence rules: an exact set is not automatically a
  confident one. If several distinct invoice sets sum exactly to a
  wire that names none of them, the result is a proposal for a person,
  never a posting. Matches reached on weak evidence (a fuzzy payer
  name, a whole-ledger search) carry capped confidence below the
  auto-post bar. A run is also idempotent by construction: payments
  that already carry a match or exception record in the workspace are
  never solved twice, and an auto-posted match settles its invoices
  immediately, so no later run can allocate them again.
- Processing order: a batch is solved in evidence order, never in the
  order the wires happen to sit in the file. Wires that name their
  invoices (or their purchase order) are solved first, OCR-repaired
  references next, then payer-and-amount matches, fuzzy payer matches,
  and whole-ledger searches last. An unreferenced wire can therefore
  never consume an invoice that a referenced wire in the same batch
  was sent to pay. The order used is recorded in the Matching Agent's
  evidence for every run.
- Settlement on approval: approving a fully covered match settles its
  invoices. Approving a PARTIAL payment does not: the applied amount
  is attributed across the lines (pro-rata, with the last line taking
  the rounding remainder) and each invoice stays open with its
  balance reduced by what was actually applied, so the unpaid
  remainder survives as a live receivable in the ledger, the
  forecast and future candidate pools. An overpayment settles its
  invoices in full; the excess is the customer's on-account credit.
- Unearned discounts: when a solution takes an early payment discount
  on an invoice whose discount window had already closed (the invoice
  is past its due date), the discount is not treated as earned. It is
  recorded on the match and, where the payment carries no claim of
  its own, claimed back through the deduction machinery as reason
  code RC-12 (Unearned Discount), with the same expected-value
  decision as any other claim.
- Exact re-verification: solver tolerances can accept a set that is a
  few cents short at seven-figure amounts. The engine therefore
  re-checks every returned set in exact integer arithmetic and rejects
  any set that does not reconcile, retrying a bounded number of times
  before returning an honest no-match with a note. This guard has its
  own regression test.
- Outcomes: an exact or policy-clean solution posts or holds per policy;
  a partial solution holds with its residual; an unsolvable payment
  becomes a reasoned refusal with zero posting lines.
- Counterfactuals: for any invoice not chosen, the engine derives why
  not (amount, age, discount and residual arithmetic), shown as the
  why-not explanation.
- Greedy baseline: a simple first-fit matcher is kept permanently. The
  evaluations endpoint runs both over labelled cases and reports the
  comparison; the product's benchmark claims come only from that
  comparison.
- Rust kernel: the subset-sum step also exists as a small Rust program,
  called over stdio with a JSON payload. Its role is precise: it is a
  verified drop-in accelerator for that step, proven equivalent to the
  Python implementation on a 203-case shared suite and re-probed live
  (24 cases) by the diagnostics endpoint on every check. The production
  hot path runs the MILP over exact sets enumerated in the engine; the
  kernel is not claimed to be in that path.

## 6. Deduction intelligence
A claimed deduction is classified into a reason-code taxonomy by keyword
evidence, with the candidates and confidence recorded. The claimed amount
is compared with the customer's claim history using a z-score; a spike
above 2.5 is flagged anomalous. The dispute decision uses an
expected-value rule: win probability times the claim, less the cost of
pursuing it, against a threshold. The win probability is a transparent
heuristic (0.94 when proof of delivery is verified clean, 0.35
otherwise) and is labelled as a heuristic in the data, on screen and in
every document the system composes. Small amounts inside a configured
tolerance are written off by policy; nothing about this chain is hidden
inside a model.

## 7. AI services, and their limits
One client wrapper carries every AI call: the key comes from the server
environment only, requests have a client timeout set below the hosting
platform's request ceiling, output length is capped, and the model's
configured name is read from the environment so operations can change it
without a code change.

- Remittance parsing: Gemini returns schema-bound JSON for payer,
  amount, references and deductions. A deterministic verifier then checks
  the result: totals must reconcile with the extracted fields, and every
  invoice or PO reference must exist in the open ledger. Invented
  references are flagged by name. If the AI call fails, times out, is
  rate limited or fails verification, a deterministic parser (patterns
  and rules, no AI) produces the extraction instead, and the response
  states which source produced it and why. The health endpoint reports
  the AI mode and the last AI error at all times.
- File intake: uploads arrive as PDF (text layer), PNG or JPG (OCR),
  plain text or email files. Extraction feeds the same verifier.
- Draft composition: dispute, inquiry and reminder texts are composed
  from the record, by the AI when available and by grounded templates
  otherwise. The reviewer always sees which source wrote a draft.
- The assistant: answers are built from the product's own records
  (matches, exceptions, forecast, the live approvals queue), with
  citations to those records, and questions outside the records are
  refused plainly. It reads live state, so an answer about the queue
  reflects decisions already taken. It cannot post, approve or send
  anything.

## 8. Forecast and collections
The forecast consumes only the residual ledger: the invoices still open
after the latest run, with settled invoices removed by the same records
the run produced. It projects eight weeks using a payment-delay model
(mean absolute error 2.95 days against a 7.67-day naive baseline on the
labelled generator), runs a Monte Carlo simulation for P10, P50 and P90
bands, and accepts what-if changes (a payment arriving, a dispute
settling) against the same position. Collections priorities and dunning
segments derive from the same residual set, so the forecast, the ledger
and the mail hub cannot quietly disagree. Each invoice is predicted
from its own facts: its amount, its own payment terms derived from its
issue and due dates (clamped to the range the model was validated on),
and the current calendar month. A customer the model has never seen is
scored with no customer-specific component, never with another
customer's behaviour borrowed under its name. A partially paid invoice
forecasts at its remaining balance, and the ledger shows the partial
application (amount applied against the original invoice total) on the
invoice's own row.

## 9. The SAP posting pack
For every cleared payment, the posting builder creates a DZ clearing
document whose journal lines come from the match's own derivation
equation (cash, discount, deduction, residual). Because the inputs
already reconcile, debits equal credits by construction, and the builder
asserts the balance on every document. The balancing line follows the
residual's direction: an underpayment's remainder posts as a residual
receivable (the customer still owes it, and it stays visible), an
overpayment's excess posts as a customer on-account credit. Neither is
parked in generic suspense; suspense is reserved for wires that match
nothing at all. Each document carries the full
BAPI_ACC_DOCUMENT_POST payload in the shape an S/4HANA system expects.
Disputed deductions produce a separate reserve journal that reclassifies
the claimed amount to disputed receivables (ASC 606 / IFRS 15), leaving
revenue untouched. Approving a refusal creates no document at all. The
pack is produced for review; writing it into a live ERP is the connector
track, stated as such in the PRD.

## 10. Mail and the outbox
Every send intent is written to a per-tenant outbox with its kind, its
reference and its text. Until SMTP credentials are configured, sends are
recorded with the status recorded, not sent, and the reason is stored
with the record and shown in the audit export. The status sent is used
only when a mail server has accepted the message. All sends, in either
state, are audit events.

## 11. Enterprise controls
- Tenancy: one SQLite database per tenant; nothing crosses tenants.
- Authentication: API keys are SHA-256 hashed at rest and shown once at
  issuance. Roles: viewer, analyst, approver, admin. When no bootstrap
  key is configured, the deployment runs in an explicitly labelled
  demo-open posture (the health response says so); secured mode is the
  same build with the key set.
- Approvals: maker-checker is policy, not code. The threshold lives in
  the tenant's policy, is snapshotted into every run, and a decision on
  a held match settles invoices (in full, or to the extent paid for a
  partial payment), issues the posting document and writes
  an audit entry whose content fingerprint lets anyone recompute and
  verify the entry later.
- Limits and observability: per-key rate limiting (300 requests per
  minute by default), a request ID on every call, structured JSON logs,
  Prometheus metrics at /metrics, a readiness check at /ready, and a
  diagnostics endpoint that reports dependency state, the kernel probe
  and the AI mode.
- Export: the audit and SAP bundle is refused with a clear conflict
  response until a run exists, because an export with nothing behind it
  would be a hollow artefact.

## 12. Frontend
A static single page (fourteen screens) served by the API process. It
holds no business logic of its own: every figure is fetched from the
API, and asset URLs carry version stamps so a new deployment is never
masked by a browser cache. Interface state that must survive navigation
(brief open or closed, mail category, draft sequence) is kept in the
page session and guarded by sequence counters, so a slow response can
never overwrite a newer screen.

## 13. Build and release
The test suite (133 automated tests, plus the Rust kernel tests) gates
the container build in continuous integration: a failing suite means no
image. The image is built from the repository's Dockerfile in two stages
(Rust kernel first, then the Python application with the kernel binary
and OCR engine placed inside). Deployment is a service update on the
hosting platform; there is no in-place mutation of a running version.

## 14. Failure semantics, as built
- Solver cannot solve a payment: the run completes, that payment is a
  refusal or an exception with its reason, and the run summary counts
  it. Never a server error.
- AI unavailable at any point: the deterministic path answers, the mode
  is labelled, and the error is visible on the health endpoint.
- A duplicate payment: stopped before matching, recorded as an
  exception, and never double-posted. Re-running a batch with the same
  idempotency key returns the original run.
- An approval on a refusal: parks the amount in suspense with an audit
  entry and no posting document.
- Data on the demonstration host is ephemeral by design (see the
  Deployment Guide); a case reload restores the full demonstration in
  one action.

## 15. Scaling path (design, honestly labelled)
The following are designs, not built software: stateless API replicas
behind a shared queue and a shared rate-limit and metrics store
(Redis-class); tenant databases migrated to Postgres (the schema avoids
SQLite-only types in domain code for this reason); solver time budgets
per payment with a documented heuristic handoff for very large candidate
sets. The single-instance version is exact about its own limits in the
Implementation Guide.
