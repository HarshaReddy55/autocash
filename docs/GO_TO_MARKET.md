# AutoCash - Go-To-Market Plan
AutoCash product pack, document 7 of 8. Previous: AWS Deployment
Runbook. Next: Build Challenges and How Each Was Resolved.
Status: founder draft. Pricing is a hypothesis to validate in pilot
calls, not a published price list. No customer results exist yet, and
none are claimed anywhere in this plan.

## Positioning
For mid-market finance teams (roughly $20M to $500M revenue) whose AR
analysts spend days each week matching payments by hand, AutoCash is an
autonomous cash application agent that matches payments to invoices
with a mathematical guarantee (every cent accounted for, a zero
residual target), explains every decision, and routes only true
exceptions to people. Unlike black-box AI matchers, AutoCash's AI
proposes and its deterministic solver decides, so an auditor can
replay every posting. The market evidence supports the wedge: vendors
advertise 90 percent plus auto-match, while independent analyst
benchmarking (The Hackett Group, 2025) measures a median near 70
percent. The distance between those two numbers is where this product
competes.

## Wedge
Start where the pain is provable in one meeting: split payments and
deduction-heavy payers. The labelled evaluation harness lets a prospect
run their own historical payments against their own open ledger in a
sandbox tenant and see the match accuracy on their data before any
contract. No incumbent offers that evaluation openly.

## Packaging hypothesis (to validate)
- The pilot is "the replay": a fixed-fee (or free) CSV replay of the
  customer's last 90 days of payments against their open ledger,
  showing the touchless rate, the residual dollars and every
  exception, before any ERP project. This attacks the segment's worst
  complaint directly: reviewers report the category leader averaging
  about 8 months to implement and 16 months to ROI.
- Pricing as a differentiator: nobody in this segment publishes
  pricing (all nine leading vendors are quote-only per a 2026
  comparison), third-party estimates put enterprise deployments at
  $200k to $500k per year and mid-market tools at roughly $1,000 to
  $5,000 per month. AutoCash can be the only serious cash application
  product with a public price: a platform fee plus per-payment
  pricing, published on the site.
- Subscription: per tenant, monthly, tiered by monthly payment volume
  (indicative bands: up to 5k payments, up to 25k, enterprise
  unlimited), priced against the analyst hours replaced, not per seat.
- Services: ERP connector setup (SAP, Oracle, NetSuite) as paid
  onboarding, sold only after the replay has proved value on the
  customer's own data.

## Proof assets (all real, from this repository and its live demo)
- A working product with a live public demonstration on AWS: the full
  fourteen-screen interface over a live API, including the SAP posting
  pack, the outbound mail hub, the forecast and the grounded
  assistant.
- Live AI, proven as live: remittance parsing served by Gemini with a
  deterministic verifier behind it, and a health endpoint that shows
  the AI mode and its last error, so the claim can be checked rather
  than believed.
- The evaluation report: the MILP solver at 100 percent against the
  greedy baseline's 80 percent on labelled scenarios; model metrics
  with their data basis stated (delay MAE 2.95 days against a 7.67-day
  baseline; validity AUC 0.846).
- 134 automated tests gating every build, the Rust kernel's 203-case
  equivalence suite, and this document pack: PRD, research,
  architecture, implementation, deployment and the builder's
  challenges account.

## First 10 customer motion
1. Warm introductions through the founder network to heads of finance
   and AR managers at mid-market product and distribution companies.
2. Offer the sandbox evaluation on their own data (no integration
   needed: CSV in, report out).
3. Convert evaluations that beat their current match rate into paid
   pilots with written success criteria.
4. The first pilot's measured results, with permission, become the
   case study. Until then, marketing uses only the repository's
   labelled synthetic results, described as such.

## Objection handling (honest answers)
- "Is this another AI demo?" No. The matching core is a MILP solver
  that re-verifies its own answers in exact cents, plus a Rust kernel
  with an equivalence suite. AI is confined to parsing, drafting and
  assistance, behind a verifier, and the product works in full with
  the AI switched off.
- "What about our ERP?" Today: CSV and API in, and a balanced SAP
  posting pack out (DZ journals and the full BAPI payload), reviewed
  by your team before anything is posted. Direct write-back is paid
  connector onboarding.
- "Security?" One database per tenant, hashed API keys, role-based
  access, maker-checker approvals, a fingerprinted audit log, and no
  external AI call unless you configure one.
- "Your headline rate?" We do not lead with one. Run the evaluation on
  your data; the number it prints is the claim.

## Competitive frame
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
