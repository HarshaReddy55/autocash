# AutoCash - Go-To-Market Plan
AutoCash product pack, document 7 of 8. Previous: AWS Deployment
Runbook. Next: Build Challenges and How Each Was Resolved.
Status: founder draft. Packaging below is structure, not a price list:
no prices are stated anywhere in this plan, because none have been
validated. No customer results exist yet, and none are claimed
anywhere in this plan.

## 1. Target customer profile
Mid-market finance teams (roughly $20M to $500M revenue) in product,
distribution and services businesses, whose AR analysts spend days
each week matching payments by hand and whose month-end close carries
a visible unapplied-cash balance. Buying triggers, in the order a
founder can test them in a first call:

1. Unapplied cash at month end: wires sitting in suspense because
   split payments, PO-only references and corrupted remittance defeat
   the team's current matching.
2. Deduction leakage: buyers taking expired early-payment discounts
   and unverified shortage deductions that get written off because a
   manual investigation costs more analyst time than the claim.
3. ERP migration or shared-services consolidation: a team moving to
   S/4HANA that wants clearing entries it can audit line by line
   rather than a black-box posting service.

## 2. Positioning
For those teams, AutoCash is an autonomous cash application agent that
matches payments to invoices with a mathematical guarantee (every cent
accounted for, a zero residual target), explains every decision, and
routes only true exceptions to people. Unlike black-box AI matchers,
AutoCash's AI proposes and its deterministic solver decides, so an
auditor can replay every posting. The market evidence supports the
wedge: vendors advertise 90 percent plus auto-match, while independent
analyst benchmarking (The Hackett Group, 2025) measures a median near
70 percent. The distance between those two numbers is where this
product competes.

## 3. Sales motion: the replay
The wedge is a shadow replay on the prospect's own historical data.
No integration, no ERP credentials, no slideware: their payments,
their ledger, their number.

- Step 1 - Export: the prospect provides a CSV export of a recent
  period of payments and the open ledger they were paid against (the
  wedge as originally framed: the last 90 days of payments).
- Step 2 - Replay: the files are ingested into an isolated AutoCash
  tenant through the synonym-mapping import, and the six-agent
  pipeline runs against their real remittances.
- Step 3 - Executive value readout: the CFO office and the controller
  walk through their own transactions inside AutoCash: the touchless
  auto-post rate achieved on their data, the residual dollars and
  every exception with its reason, the unearned discounts and invalid
  short-pays the Deduction Agent caught, and balanced SAP clearing
  journals for the cleared payments.

This attacks the segment's worst complaint directly: reviewers report
the category leader averaging about 8 months to implement and 16
months to ROI (sourced in document 2). A replay produces evidence in
days, before any ERP project exists.

## 4. Commercial packaging (structure only, prices to validate)
- The Replay: the pilot itself, scoped as in section 3, with written
  success criteria agreed before it runs. It is the entry offer and
  the proof asset in one.
- Core Platform: autonomous cash application and the SAP clearing
  pack (balanced DZ journals and the full BAPI_ACC_DOCUMENT_POST
  payload), subscribed per tenant and tiered by monthly payment
  volume rather than per seat.
- Deduction Recovery module: dispute packaging with proof-of-delivery
  checks, expected-recovery valuation, and multi-tone buyer recovery
  mail composed from the run's records.
- Treasury Forecasting and Collections module: the post-reconciliation
  forecast (8-week, P10/P50/P90) and the collections worklist derived
  from the same residual ledger.
- Services: ERP connector setup (SAP, Oracle, NetSuite) as paid
  onboarding, sold only after the replay has proved value on the
  customer's own data.

Pricing approach, as a hypothesis to validate in pilot calls: nobody
in this segment publishes pricing (all nine leading vendors are
quote-only per a 2026 comparison, sourced in document 2), so a
published platform fee plus per-payment pricing, tiered by volume and
priced against the analyst hours replaced, is itself a differentiator.
The figures get set after the first pilots measure the hours actually
replaced; publishing invented numbers now would break the rule the
whole pack runs on.

## 5. Proof assets (all real, from this repository and its live demo)
- A working product with a live public demonstration on AWS: the full
  fourteen-screen interface over a live API, including the SAP posting
  pack, the outbound mail hub, the forecast and the grounded
  assistant.
- Live AI, proven as live: remittance parsing served by Gemini with a
  deterministic verifier behind it, and a health endpoint that shows
  the AI mode and its last error, so the claim can be checked rather
  than believed.
- The evaluation report: the MILP solver at accuracy 1.0 against the
  greedy baseline's 0.8 on labelled ground-truth cases, computed live
  by the evaluations endpoint; model metrics with their data basis
  stated (delay MAE 2.948 days against a 7.665-day baseline; validity
  AUC 0.846, on a disclosed synthetic generator).
- 134 automated tests across 29 modules gating every build, the Rust
  kernel's 203-case equivalence suite, and this document pack: PRD,
  research, architecture, implementation, deployment and the builder's
  challenges account.

## 6. First 10 customer motion
1. Warm introductions through the founder network to heads of finance
   and AR managers at mid-market product and distribution companies.
2. Offer the replay on their own data (no integration needed: CSV in,
   report out).
3. Convert replays that beat their current match rate into paid pilots
   with written success criteria.
4. The first pilot's measured results, with permission, become the
   case study. Until then, marketing uses only the repository's
   labelled synthetic results, described as such.

## 7. Objection handling (honest answers)
- "Is this another AI demo?" No. The matching core is a MILP solver
  that re-verifies its own answers in exact cents, plus a Rust kernel
  with an equivalence suite. AI is confined to parsing, drafting and
  assistance, behind a verifier, and the product works in full with
  the AI switched off.
- "What about our ERP?" Today: CSV and API in, and a balanced SAP
  posting pack out (DZ journals and the full BAPI payload), reviewed
  by your team before anything is posted. Direct write-back is paid
  connector onboarding.
- "Security?" One database per tenant, hashed API keys shown once,
  role-based access, maker-checker approvals, a fingerprinted audit
  log, and no external AI call unless you configure one.
- "Your headline rate?" We do not lead with one. Run the evaluation on
  your data; the number it prints is the claim.

## 8. Competitive frame
From the research document in this pack, with vendor claims labelled
as such: incumbents compete on headline auto-match rates that have
plateaued and on platform breadth. The open ground is (1) the
exception tail, productised with counterfactual explanations and a
public evaluation harness; (2) provable correctness instead of
probabilistic confidence; (3) mid-market self-serve deployment in
days; (4) policy as configuration owned by the customer. AutoCash is
deliberately built on exactly those four. Where incumbents are ahead
(ERP connector depth, bank-file formats, SOC 2), the PRD lists them
as roadmap rather than pretending parity.

Version 3.0 | 3 Nov 2026 | Owner: C. Harsha Vardhana Reddy
