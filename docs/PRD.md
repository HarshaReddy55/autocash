# AutoCash - Product Requirements Document
AutoCash product pack, document 1 of 8. Next: Market and Segment Research.
Version 2.0 | 2 Nov 2026 | Owner: C. Harsha Vardhana Reddy

## 1. The problem
Cash application is the work of matching each incoming payment to the open
invoices it pays. In most mid-market finance teams it is still done by hand:
an analyst reads remittance emails and bank lines, hunts through the ledger,
and keys the result into the ERP. It is slow, it is error prone, and every
unapplied payment distorts the collections queue and the cash forecast.

The market context, stated carefully. Vendors in this category advertise
auto-match rates of 90 percent and above. Independent analyst benchmarking
tells a different story: The Hackett Group (2025) measured a median
auto-match rate near 70 percent across finance organisations, with the top
third above 80 percent. The gap between the advertised number and the
measured one is the problem this product is built on. The hard part of cash
application is not the payments that match. It is the tail that does not,
and what a team can prove about every decision afterwards.

## 2. Product thesis
Cash application is a conservation problem with an information problem on
top. Every cent received must land somewhere auditable: an invoice, a
discount, a deduction, or an explained residual. But the evidence arrives as
messy remittance text, often incomplete, sometimes wrong.

So the product separates proposing from deciding. Probabilistic components
(an AI parser, prediction models) may propose. Deterministic components (an
optimisation solver, accounting policy) decide, and they must reconcile to
the cent. Anything that cannot be reconciled becomes a tracked exception
with a recommended action. Nothing is silently written off, and no figure
in the product is typed in by hand: every number on every screen is
computed from the run in front of the user.

## 3. Users
- AR analyst: loads receipts, runs reconciliation, works the approvals and
  exception queues, needs a plain explanation for every outcome.
- AR manager or approver: owns policy thresholds, gives the second approval
  on high-value postings, reviews disputes before they are sent.
- CFO office: needs the cash forecast, the collections priorities and the
  dispute exposure, all derived from the same ledger the analysts use.
- IT and integrators: API keys, ERP posting formats, audit exports.

## 4. What the product does today
All of the following is built, tested and running in this repository.

1. A staged workspace. Loading a case stages its invoices and payments and
   changes nothing else. Reconciliation runs only when the user executes
   it. Every screen states plainly which stage the workspace is in, and
   actions that need a completed run say so instead of showing stale data.
2. A six-agent pipeline (Capture, Linking, Matching, Deduction, Policy,
   Briefing). Each agent's work is recorded per run with its inputs, its
   result and its measured time, and can be inspected on screen.
3. A matching engine built on mixed-integer optimisation (MILP) under a
   cash conservation equation, working in exact integer cents. Candidate
   invoices are restricted per payment before solving. Every set the
   solver returns is re-verified in exact cents before it is believed.
   A greedy matcher is kept permanently as the benchmark the solver must
   beat, and every non-match carries a counterfactual explanation of why
   a given invoice was not chosen.
4. Refusals as first-class outcomes. When nothing in the ledger explains a
   payment, the engine issues a reasoned refusal instead of forcing a
   match. Approving a refusal parks the money in suspense with an audit
   entry. No posting document is ever created for money no invoice
   supports.
5. Deduction intelligence. Claims are classified into a reason-code
   taxonomy with confidence, measured against the customer's history with
   a z-score anomaly check, and valued by an expected-recovery rule. The
   win probability behind that rule is a transparent heuristic and is
   labelled as one everywhere it appears; it is not a trained model.
6. An SAP posting pack. Every cleared payment produces a balanced DZ
   clearing document and the full BAPI_ACC_DOCUMENT_POST payload an
   S/4HANA system would receive, plus the ASC 606 / IFRS 15 reserve
   journal for disputed deductions. Debits equal credits by construction,
   because the amounts come from the match's own derivation.
7. An outbound mail hub. Dispute claims, unidentified-wire inquiries,
   settlement confirmations and dunning reminders are composed from the
   run's records, in selectable tones, ready for review. Until a mailbox
   is configured, a send is recorded as recorded, not sent, with the
   reason shown. The product never claims a mail was sent when it was not.
8. Forecast and collections. The forecast reads only the residual ledger
   left after reconciliation, over an 8-week horizon, with Monte Carlo
   P10/P50/P90 bands and a what-if view. Collections priorities and
   dunning come from the same residual position, so every screen agrees.
9. A grounded assistant. It answers questions from the product's own
   records, cites them, refuses questions the records cannot answer, and
   reads live state: if a match has been decided, its answer about the
   approvals queue reflects that decision immediately.
10. AI remittance parsing with a verifier. Gemini extracts structured
    fields from remittance text (typed, pasted, or read from PDF and
    image files by OCR). A deterministic verifier then checks every
    extracted reference against the open ledger. If the AI is unavailable,
    slow or wrong, a deterministic parser produces the answer instead and
    the response says so. The AI never posts anything.
11. An enterprise layer. One database per tenant; per-browser-session
    workspaces so two reviewers never disturb each other; API keys hashed
    at rest; role-based access (viewer, analyst, approver, admin);
    per-key rate limiting; maker-checker approvals; an audit log whose
    decision entries carry a content fingerprint; and a one-click export
    of the full audit and SAP bundle.
12. Evaluation and health surfaces. A labelled benchmark compares the
    solver against the greedy baseline case by case. A diagnostics view
    reports the state of every dependency, including a live equivalence
    probe of the Rust acceleration kernel and the current AI mode and
    last AI error. Nothing in the product hides which mode it is in.

The interface presents this as fourteen screens in three groups: Operate
(Dashboard, Use Cases, Upload Center, Run Reconciliation, SAP BAPI and
EBRR, Outbound Mail Hub), Insight and Governance (Ledger, Forecast and
Collections, Policy Studio), and Evals and Architecture (Evaluations,
Agent Health, Methodology, Architecture, Product Thinking).

## 5. Measured results
Verified on labelled synthetic data in this repository. These are
engineering verification figures, not customer results; no customer metric
may be quoted until a pilot produces one.

- Matching benchmark: the MILP solver scores 100 percent against the
  greedy baseline's 80 percent on the labelled scenario set, computed
  live per call by the evaluations endpoint.
- Payment-delay model: mean absolute error 2.95 days against 7.67 days
  for a naive baseline. Deduction-validity model: AUC 0.846. Basis: a
  synthetic generator with a learnable signal, 960 training rows and 240
  held-out rows in time order.
- The built-in demo case (one realistic day of receipts: 19 invoices,
  $1,003,430 open; 16 payments, $682,135 received): 10 payments post
  themselves, 5 are solved and held for a person, 1 duplicate is stopped
  before matching. Autonomous resolution is 93.8 percent, counted as
  zero-touch postings plus solved-and-held matches plus reasoned
  refusals, over all 16 payments. The definition is printed in the
  product next to the figure.
- Test suite: 134 automated tests plus the Rust kernel tests, all
  passing, and the suite gates every production build.

North star for the product: the touchless cash rate at zero residual.

## 6. Non-goals for this version
- Live ERP write-back. Posting payloads are produced, balanced and ready
  for review; direct posting into SAP, Oracle or NetSuite is the
  integration track that follows.
- Bank feed formats. Lockbox, BAI2 and MT940 parsers are roadmap; CSV,
  API and file ingestion (including OCR) are live.
- A trained dispute-outcome model. The win probability is a labelled
  heuristic until real dispute outcomes exist to train on.
- Shared multi-instance state. Rate limiting and metrics are exact for a
  single instance; the shared-store design is specified in the
  Architecture document and labelled there as design, not product.

## 7. Risks and how the product answers them
- AI invents a reference: the verifier checks every reference against the
  open ledger before anything is staged, and parsing never posts.
- The solver accepts an almost-right answer: every returned set is
  re-verified in exact integer cents; a set that does not reconcile is
  rejected and the payment is routed to a person with the reason.
- A reviewer shares one link with many people: workspaces are isolated
  per browser session, and the demo posture is a stated choice, with a
  secured mode (bootstrap key, per-tenant API keys) available in the
  same build.
- Figures drift between screens: every surface reads the same stored
  records, and the assistant reads live queue state rather than a run
  snapshot.
