# AutoCash - Go-To-Market Pack (Draft v1)
Status: founder draft. Pricing is a hypothesis to validate in pilot calls,
not a published price list. No customer results exist yet; none are claimed.

## Positioning
For mid-market finance teams (roughly $20M to $500M revenue) whose AR analysts
spend days each week matching payments by hand, AutoCash is an autonomous
cash application agent that matches payments to invoices with a mathematical
guarantee (every cent accounted for, $0-residual target), explains every
decision, and routes only true exceptions to humans. Unlike black-box AI
matchers, AutoCash's AI proposes and deterministic solvers dispose - so an
auditor can replay every posting.

## Wedge
Start where pain is provable in one meeting: split payments and
deduction-heavy payers. The labelled evaluation harness lets a prospect run
their own historical payments against their own open ledger in a sandbox
tenant and see match accuracy on THEIR data before any contract.

## Packaging hypothesis (to validate)
- Pilot = "the replay": a fixed-fee (or free) CSV replay of the customer's
  last 90 days of payments against their open ledger, showing touchless
  rate, residual dollars and every exception, before any ERP project. This
  attacks the segment's worst complaint directly: G2 reviewers report
  HighRadius AR averaging about 8 months to implement and 16 months to ROI.
- Pricing as a differentiator: nobody in this segment publishes pricing
  (all nine leading vendors are quote-only per a 2026 comparison), and
  third-party estimates put enterprise deployments at $200k to $500k per
  year and mid-market tools at roughly $1,000 to $5,000 per month.
  AutoCash can be the only serious cash application product with a public
  price: a platform fee plus per-payment pricing, published on the site.
- Subscription: per-tenant monthly, tiered by monthly payment volume
  (indicative bands: up to 5k payments, up to 25k, enterprise unlimited),
  priced against the analyst hours replaced, not per-seat.
- Services: ERP connector setup (SAP, Oracle, NetSuite) as paid onboarding,
  sold only after the replay has proved value on the customer's own data.

## Proof assets (all real, from this repo)
- Working product with live API and frontend (deployable demo tenant).
- Evaluation report: MILP 100% vs greedy 80% on labelled scenarios;
  model metrics with stated data basis; 19 automated tests; Rust kernel
  equivalence proof (203 cases).
- Architecture and PRD documents showing enterprise readiness (tenancy,
  RBAC, audit, observability).

## First 10 customer motion
1. Warm intros via founder network to heads of finance / AR managers at
   mid-market product and distribution companies.
2. Offer the sandbox evaluation on their own data (no integration needed -
   CSV in, report out).
3. Convert evaluations that beat their current match rate into paid pilots
   with written success criteria.
4. First pilot's measured results (with permission) become the case study;
   until then, marketing uses only the repo's labelled synthetic results,
   clearly described as such.

## Objection handling (honest answers)
- "Is this another AI demo?" No: the matching core is a MILP solver and a
  Rust kernel with equivalence tests; AI is confined to parsing and
  assistance, behind a verifier.
- "What about our ERP?" CSV/API today; posting payloads are produced for
  review. Paid connector onboarding for direct write-back.
- "Security?" Per-tenant database isolation, hashed API keys, RBAC,
  audit logs, and the product runs fully without any external AI call.

## Competitive frame (from docs/RESEARCH_SEGMENT.md, vendor claims labelled)
Incumbents compete on headline auto-match rates that have plateaued (vendor
claims cluster at 85 to 99 percent) and on platform breadth. The research
brief identifies the open ground as: (1) the exception tail, productised with
counterfactual explanations and a public evaluation harness; (2) provable
correctness instead of probabilistic confidence; (3) mid-market self-serve
deployment in days; (4) policy-as-configuration owned by the customer.
AutoCash is deliberately built on exactly those four: its evaluations
endpoint IS the public harness, its MILP solver shows its proof (objective,
residual, solver status), onboarding is a CSV, and tenant policies are
versioned configuration. Where incumbents are ahead - ERP connector depth,
bank-file formats, SOC 2 - the PRD lists them as roadmap rather than
pretending parity.
