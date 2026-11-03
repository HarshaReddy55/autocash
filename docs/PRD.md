# AutoCash - Product Requirements Document
AutoCash product pack, document 1 of 8. Next: Market and Segment Research.

## 1. Executive summary
AutoCash is an autonomous cash application and deduction recovery
platform for mid-market and enterprise finance teams. Every business
day, accounts receivable (AR) teams receive bank wires and lockbox
payments while the evidence for those payments arrives separately, as
remittance emails, PDFs and spreadsheets. Analysts spend hours matching
lump-sum payments to open invoices by hand, investigating short-pays,
and keying clearing journals into the ERP.

AutoCash replaces that manual work with a six-agent pipeline (Capture,
Linking, Matching, Deduction, Policy, Briefing) built on one rule:
probabilistic components may propose, deterministic components decide.
An AI parser and prediction models suggest; a mixed-integer solver under
a cash conservation equation, working in exact integer cents, decides;
and accounting policy governs what may post without a person. Every
cent received lands somewhere auditable: an invoice, a discount, a
deduction, or an explained residual. Anything that cannot be reconciled
becomes a tracked exception with a recommended action. Nothing is
silently written off, and no figure in the product is typed in by hand:
every number on every screen is computed from the run in front of the
user.

## 2. Market context, stated carefully
Vendors in this category advertise auto-match rates of 90 percent and
above. Independent analyst benchmarking tells a different story: The
Hackett Group (2025) measured a median auto-match rate near 70 percent
across finance organisations, with the top third above 80 percent. The
gap between the advertised number and the measured one is the problem
this product is built on. The hard part of cash application is not the
payments that match. It is the tail that does not, and what a team can
prove about every decision afterwards. The full research, with sources,
is document 2 of this pack.

## 3. Product thesis
Cash application is a conservation problem with an information problem
on top. The conservation half is exact: the ledger must balance to the
cent. The information half is messy: remittance text is often
incomplete, sometimes wrong. The product therefore separates proposing
from deciding, re-verifies every solver answer in exact integer cents
before believing it, and treats refusals as first-class outcomes: when
nothing in the ledger explains a payment, the engine issues a reasoned
refusal instead of forcing a match.

## 4. Target personas and business problems

| Persona | Daily responsibility | Core pain point | AutoCash outcome |
| :--- | :--- | :--- | :--- |
| AR cash application analyst | Match the day's wires and lockbox payments to open invoices; clear exceptions | Hours spent hunting for missing remittance references, repairing OCR errors, and testing invoice combinations in a spreadsheet | Routine wires and multi-invoice split wires post automatically; exceptions arrive pre-diagnosed with a derivation and a counterfactual explanation |
| AR manager or approver | Own policy thresholds; give the second approval on high-value postings; review disputes before they are sent | Unapplied cash distorting the collections queue; write-offs taken to clear the queue rather than on merit | Maker-checker approvals with the reason for every hold stated; dispute claims valued by an expected-recovery rule before anyone sends them |
| Corporate controller | Protect general ledger integrity and close the books on time | Clearing journals that do not balance; deduction leakage buried in suspense | Every cleared payment produces a balanced DZ clearing document and the full BAPI_ACC_DOCUMENT_POST payload, built from the match's own derivation |
| CFO office | Cash forecast, collections priorities, dispute exposure | Forecasts built on stale ledger balances while cash sits unapplied | Forecast and collections computed from the post-reconciliation residual ledger, so every screen agrees with the analysts' position |
| IT and integrators | Access control, ERP posting formats, audit exports | Black-box automation that cannot be replayed or audited | Hashed API keys, role-based access, a fingerprinted audit log, and a one-click export of the audit and SAP bundle |

## 5. Core functional requirements
All of the following is built, tested and running.

1. A staged workspace. Loading a case stages its invoices and payments
   and changes nothing else. Reconciliation runs only when the user
   executes it. Every screen states plainly which stage the workspace
   is in, and actions that need a completed run say so instead of
   showing stale data.
2. A six-agent pipeline (Capture, Linking, Matching, Deduction, Policy,
   Briefing). Each agent's work is recorded per run with its inputs,
   its result and its measured time, and can be inspected on screen.
3. A matching engine built on mixed-integer optimisation (MILP) under
   a cash conservation equation, working in exact integer cents.
   Candidate invoices are restricted per payment before solving. Every
   set the solver returns is re-verified in exact cents before it is
   believed. A greedy matcher is kept permanently as the benchmark the
   solver must beat, and every non-match carries a counterfactual
   explanation of why a given invoice was not chosen.
4. Refusals as first-class outcomes. When nothing in the ledger
   explains a payment, the engine issues a reasoned refusal instead of
   forcing a match. The refusal sits in the approvals queue by design;
   approving it parks the money in suspense (GL 119900) with an audit
   entry, and it can never post to AR. No posting document is created
   for money no invoice supports.
5. Deduction intelligence. Claims are classified into a reason-code
   taxonomy (RC-02, RC-05, RC-07, RC-09, RC-11, RC-12, RC-99) with
   confidence, measured against the customer's history with a z-score
   anomaly check, and valued by an expected-recovery rule. The win
   probability behind that rule is a transparent heuristic (0.94 with a
   verified clean proof of delivery, 0.35 otherwise) and is labelled as
   a heuristic everywhere it appears; it is not a trained model.
6. An SAP posting pack. Every cleared payment produces a balanced DZ
   clearing document and the full BAPI_ACC_DOCUMENT_POST payload an
   S/4HANA system would receive, plus the ASC 606 / IFRS 15 reserve
   journal for disputed deductions. Debits equal credits by
   construction, because the amounts come from the match's own
   derivation.
7. An outbound mail hub. Dispute claims, unidentified-wire inquiries,
   settlement confirmations and dunning reminders are composed from the
   run's records, in selectable tones, ready for review. Until a
   mailbox is configured, a send is recorded as recorded_not_sent with
   the reason shown. The product never claims a mail was sent when it
   was not.
8. Forecast and collections. The forecast reads only the residual
   ledger left after reconciliation, over an 8-week horizon, with
   Monte Carlo P10/P50/P90 bands and a what-if view. Collections
   priorities and dunning come from the same residual position, so
   every screen agrees.
9. A grounded assistant. It answers questions from the product's own
   records, cites them, refuses questions the records cannot answer,
   and reads live state: if a match has been decided, its answer about
   the approvals queue reflects that decision immediately.
10. AI remittance parsing with a verifier. Gemini extracts structured
    fields from remittance text (typed, pasted, or read from PDF and
    image files by OCR). A deterministic verifier then checks every
    extracted reference against the open ledger. If the AI is
    unavailable, slow or wrong, a deterministic parser produces the
    answer instead and the response says so, labelled deterministic.
    The AI never posts anything.
11. An enterprise layer. One database per tenant; per-browser-session
    workspaces so two reviewers never disturb each other; API keys
    SHA-256 hashed at rest and shown once; role-based access (viewer,
    analyst, approver, admin); per-key rate limiting; maker-checker
    approvals; an audit log whose decision entries carry a SHA-256
    content fingerprint.
12. Evaluation and health surfaces. A labelled benchmark compares the
    solver against the greedy baseline case by case. A diagnostics
    view reports the state of every dependency, including a live
    equivalence probe of the Rust kernel and the current AI mode and
    last AI error. Nothing in the product hides which mode it is in.

## 6. Product surface (14 dedicated views)

| Group | Views |
| :--- | :--- |
| OPERATE | 01 Dashboard, 02 Use Cases, 03 Upload Center, 04 Run Reconciliation, 05 SAP BAPI & EBRR, 06 Outbound Mail Hub |
| INSIGHT & GOVERNANCE | 07 Ledger, 08 Forecast and Collections, 09 Policy Studio |
| EVALS & ARCHITECTURE | 10 Evaluations, 11 Agent Health, 12 Methodology, 13 Architecture, 14 Product Thinking |

## 7. Measured results (flagship case and benchmarks)
Verified on labelled synthetic data in this repository. These are
engineering verification figures, not customer results; no customer
metric may be quoted until a pilot produces one.

The built-in demo case is one realistic day of receipts: 19 open
invoices totalling $1,003,430 of open AR, and 16 incoming payments
totalling $682,135. A run of that case produces:

- 10 payments auto-posted, totalling $411,800: a touchless rate of
  62.5 percent of payments.
- 5 payments solved and held for one-click maker-checker sign-off,
  totalling $223,150, each with the reason for the hold stated (a
  partial payment, two maker-checker value holds, an overpayment, and
  one reasoned refusal).
- 1 duplicate payment blocked before matching by its fingerprint.
- Autonomous resolution of 93.8 percent (15 of 16 payments), counted
  as zero-touch postings plus solved-and-held matches plus reasoned
  refusals over all 16 payments. The definition is printed in the
  product next to the figure.
- The flagship dispute in the case: a $4,200 claim at a 0.94 win
  probability (the labelled heuristic, proof of delivery verified
  clean), giving $3,903 of expected recovery after the $45 processing
  cost.

Benchmarks, computed live by the product's own endpoints:

- Matching: the MILP solver scores accuracy 1.0 against the greedy
  baseline's 0.8 on the 10 labelled ground-truth cases behind the
  evaluations endpoint. All 10 scenario packs pass their checks.
- Payment-delay model: mean absolute error 2.948 days against 7.665
  days for a naive baseline. Deduction-validity model: AUC 0.846.
  Basis, disclosed in the product: a synthetic generator with a
  learnable signal, 1,200 rows (960 training, 240 held out), six
  customer profiles. Retrain on real history when available.
- Test suite: 134 automated tests across 29 modules, plus 4 Rust
  kernel tests, all passing, and the suite gates every production
  build in CI.

North star for the product: the touchless cash rate at zero residual.

## 8. Non-goals for this version
- Live ERP write-back. Posting payloads are produced, balanced and
  ready for review; direct posting into SAP, Oracle or NetSuite is the
  integration track that follows.
- Bank feed formats. Lockbox, BAI2 and MT940 parsers are roadmap; CSV,
  API and file ingestion (including OCR) are live.
- A trained dispute-outcome model. The win probability is a labelled
  heuristic until real dispute outcomes exist to train on.
- Shared multi-instance state. Rate limiting and metrics are exact for
  a single instance; the shared-store design is specified in the
  Architecture document and labelled there as design, not product.

## 9. Risks and how the product answers them
- AI invents a reference: the verifier checks every reference against
  the open ledger before anything is staged, and parsing never posts.
- The solver accepts an almost-right answer: every returned set is
  re-verified in exact integer cents; a set that does not reconcile is
  cut and the solver retries (at most 6 attempts) before the payment
  is routed to a person with the reason.
- A reviewer shares one link with many people: workspaces are isolated
  per browser session, and the demo posture is a stated choice, with a
  secured mode (bootstrap key, per-tenant API keys) available in the
  same build.
- Figures drift between screens: every surface reads the same stored
  records, and the assistant reads live queue state rather than a run
  snapshot.

## 10. Roadmap (labelled as roadmap, not product)
- Model v2: payment-delay and validity models that take the customer's
  actual workspace payment and deduction history as features, replacing
  the disclosed synthetic-only basis.
- Save & Retrieve by Session ID: named, restorable workspaces.
- Two-way ERP connectors, bank-file formats (BAI2, MT940, lockbox),
  and a formal correction-learning loop.

Version 3.0 | 3 Nov 2026 | Owner: C. Harsha Vardhana Reddy
