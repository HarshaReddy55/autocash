# Segment Research Brief - Autonomous Receivables / Cash Application
Compiled 31 Oct 2026 from vendor pages and analyst coverage (URLs in
RESEARCH_NOTES at the campaign files). ALL market figures below are vendor
claims from those sources; none are independently verified, and none are
AutoCash results.

## Players and wedges
- HighRadius: category definer, full Office-of-the-CFO platform; cash app as
  13 specialised agents; claims 90%+ straight-through; LiveCube no-code data
  layer; enterprise, custom-priced, implementation-heavy.
- BlackLine: control and close wedge; Verity AI (Remit/Match/Collect), Vera
  supervisor agent; claims about 85% auto-match, ISO/IEC 42001 AI governance.
- Esker: document intelligence wedge; deep-learning first-time recognition of
  unseen remittance layouts, teaching mode, learns from corrections.
- Quadient AR (ex-YayPay): mid-market full AR; ML suggests the customer for
  unidentified payments for human approval.
- Billtrust: payments network wedge (Business Payments Network + Digital
  Lockbox); claims top-quartile 99.6% match, 40 exceptions per analyst-hour.
- Emagia: AI-native breadth, six autonomous modules, Gia studio; claims 95%+
  auto-match, 97%+ touchless capture.
- Gaviti: collections execution only (prioritisation, adaptive dunning).
- Tesorio: predictive cash intelligence (per-invoice payment-date prediction).
- Also: Serrala (SAP-embedded), Versapay (portal-led capture).

## 2026 table stakes (per the brief)
Omnichannel ingestion (email, EDI 820/823, BAI2, MT940/CAMT, lockbox, AP
portals); two-way ERP connectors (SAP, Oracle, NetSuite, Dynamics);
multi-reference matching with correction learning; deductions as a first-class
workflow (reason codes, tolerance, validity, dispute packets, DDO); coupled
collections and forecasting; agent control plane with per-step confidence and
human-in-the-loop queues; evaluation and governance (reproducible, auditable
decisions - headline match rates have plateaued at 90 to 99 percent across
vendors, so differentiation has shifted to the residual exception tail and
auditability); SOC 2 / ISO posture, immutable audit, RBAC, maker-checker.

## White space (the brief's findings)
1. The exception tail, productised: counterfactual explanations, computed
   next-best-action, and a public reproducible golden-dataset evaluation
   harness. Open evaluation is unclaimed territory.
2. Provable correctness vs probabilistic matching: a hard-constraint
   optimiser (MILP, cash-conservation equality) that proves a posting set is
   residual-optimal and shows the proof.
3. Mid-market, self-serve, fast deployment: API-first, CSV/BAI2 onboarding in
   days, transparent per-remittance pricing, no ERP modification.
4. Governed policy-as-configuration: solver weights and thresholds as
   versioned, audited configuration (not vendor-owned by any AR vendor).
5. Deployment model: bring-your-own-cloud / VPC, open APIs.
6. Regional depth (inference, flagged as such in the brief): UPI/NEFT
   reference formats, Tally/Zoho/local ERPs, GST artefacts absent from
   US-centric leaders.

## How AutoCash maps today (honest)
- Owns white space 1, 2 and 4 already: counterfactual why-not explanations,
  a live golden-dataset evaluations endpoint, MILP with solver status and
  residual proof, tenant policies as versioned configuration with audit.
- Aligned with 3 and 5: CSV onboarding live, Docker/BYOC deployment packaged.
- Gaps vs table stakes (roadmap, stated in PRD non-goals): BAI2/EDI/lockbox
  ingestion parsers, two-way ERP connectors with native posting payloads,
  SOC 2 posture (process, not code), correction-learning loop formalisation.

## Pricing signals (second research pass, 31 Oct 2026, sourced)
- Almost nobody in this segment publishes pricing (Rankite 2026 comparison:
  none of nine leading vendors publish prices; all require a sales cycle).
- HighRadius: no rate card; public model is outcome-based (vendor claim:
  $0 implementation and $0 subscription until go-live, then fees tied to
  agreed success criteria). Third-party estimates (NOT vendor-published):
  roughly $200k to $500k per year for enterprise deployments.
- Billtrust: quote-only; third-party estimates roughly $20k to $60k per year
  base for mid-market, processing extra.
- BlackLine, Esker, Emagia, Quadient AR, Gaviti: all quote-based, sized on
  volume, entities, modules, users. No public per-payment rate found.
- Category pattern: per-seat is not standard; lighter mid-market
  subscriptions broadly $1,000 to $5,000 per month (third-party estimates).
- Implementation pain (reviewer-reported, G2): HighRadius AR averages about
  8 months to implement and 16 months to ROI; configuration changes can
  require vendor consulting at extra cost. Practitioner analysis names
  black-box audit risk as a core limitation of AI cash application.
