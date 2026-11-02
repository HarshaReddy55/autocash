# AutoCash - Market and Segment Research
AutoCash product pack, document 2 of 8. Previous: Product Requirements
Document. Next: Architecture and System Design.
Compiled 31 Oct 2026 from vendor pages and analyst coverage; the AutoCash
mapping at the end was updated 2 Nov 2026. All market figures below are
vendor claims or analyst findings from those sources. None are
independently verified by us, and none are AutoCash results.

## The measured reality behind the marketing
Vendors in this category advertise auto-match rates between 85 and 99
percent. Independent analyst benchmarking is more sober: The Hackett
Group (2025) measured a median auto-match rate near 70 percent across
finance organisations, with the top third above 80 percent. Any product
conversation in this segment should start from the measured number, not
the advertised one, and should treat the unmatched tail, not the headline
rate, as the real battleground.

## Players and wedges
- HighRadius: category definer, full Office-of-the-CFO platform; cash
  application as 13 specialised agents; claims 90 percent plus
  straight-through processing; LiveCube no-code data layer; enterprise,
  custom priced, implementation heavy; pricing moved to an outcome-based
  model in 2026.
- BlackLine: control and close wedge; Verity AI (Remit, Match, Collect),
  Vera supervisor agent; claims about 85 percent auto-match; ISO/IEC
  42001 AI governance.
- Esker: document intelligence wedge; deep-learning first-time recognition
  of unseen remittance layouts, teaching mode, learns from corrections.
- Quadient AR (formerly YayPay): mid-market full AR; ML suggests the
  customer for unidentified payments, for human approval.
- Billtrust: payments network wedge (Business Payments Network and
  Digital Lockbox); claims top-quartile 99.6 percent match, 40 exceptions
  per analyst-hour.
- Emagia: AI-native breadth, six autonomous modules, Gia studio; claims
  95 percent plus auto-match, 97 percent plus touchless capture.
- Gaviti: collections execution only (prioritisation, adaptive dunning).
- Tesorio: predictive cash intelligence (per-invoice payment-date
  prediction).
- Also: Serrala (SAP-embedded), Versapay (portal-led capture).

## 2026 table stakes (per the brief)
Omnichannel ingestion (email, EDI 820/823, BAI2, MT940/CAMT, lockbox, AP
portals); two-way ERP connectors (SAP, Oracle, NetSuite, Dynamics);
multi-reference matching with correction learning; deductions as a
first-class workflow (reason codes, tolerance, validity, dispute packets);
coupled collections and forecasting; an agent control plane with per-step
confidence and human-in-the-loop queues; evaluation and governance
(reproducible, auditable decisions; headline match rates have plateaued
across vendors, so differentiation has shifted to the residual exception
tail and to auditability); SOC 2 / ISO posture, immutable audit, RBAC,
maker-checker.

## White space (the brief's findings)
1. The exception tail, productised: counterfactual explanations, a
   computed next-best-action, and a public, reproducible evaluation
   harness on labelled data. Open evaluation is unclaimed territory.
2. Provable correctness over probabilistic matching: a hard-constraint
   optimiser (MILP, cash-conservation equality) that proves a posting set
   is residual-optimal and shows the proof.
3. Mid-market, self-serve, fast deployment: API-first, CSV onboarding in
   days, transparent pricing, no ERP modification.
4. Governed policy as configuration: solver weights and thresholds as
   versioned, audited configuration, owned by the customer. No AR vendor
   owns this today.
5. Deployment model: bring-your-own-cloud, open APIs.
6. Regional depth (inference, flagged as such in the brief): UPI and NEFT
   reference formats, Tally, Zoho and local ERPs, GST artefacts, all
   absent from US-centric leaders.

## Pricing signals (second research pass, 31 Oct 2026, sourced)
- Almost nobody in this segment publishes pricing (a 2026 comparison of
  nine leading vendors found none publishing prices; all require a sales
  cycle).
- HighRadius: no rate card; the public model is outcome-based (vendor
  claim: no implementation or subscription fee until go-live, then fees
  tied to agreed success criteria). Third-party estimates, not
  vendor-published, put enterprise deployments at roughly $200k to $500k
  per year.
- Billtrust: quote-only; third-party estimates of roughly $20k to $60k
  per year base for mid-market, processing extra.
- BlackLine, Esker, Emagia, Quadient AR, Gaviti: all quote-based, sized
  on volume, entities, modules and users. No public per-payment rate
  found.
- Category pattern: per-seat pricing is not standard; lighter mid-market
  subscriptions run broadly $1,000 to $5,000 per month (third-party
  estimates).
- Implementation pain (reviewer-reported, G2): HighRadius AR averages
  about 8 months to implement and 16 months to ROI; configuration
  changes can require vendor consulting at extra cost. Practitioner
  analysis names black-box audit risk as a core limitation of AI cash
  application products.

## How AutoCash maps today (updated 2 Nov 2026, honest)
- Owns white space 1, 2 and 4. Counterfactual why-not explanations on
  every non-match; a live, labelled evaluation endpoint any reviewer can
  run; a MILP solver that re-verifies its own answers in exact cents and
  shows its derivation; tenant policy as versioned, audited
  configuration.
- Aligned with 3 and 5. CSV and file onboarding is live (including OCR of
  PDF and image remittances), and the product ships as one container
  image that runs on the customer's own cloud account.
- Built since this brief was first compiled: the SAP posting pack
  (balanced DZ journals, the full BAPI_ACC_DOCUMENT_POST payload and the
  ASC 606 reserve journal) and the outbound mail hub, which turns run
  outcomes into dispute claims, inquiries, confirmations and dunning.
- Gaps against table stakes, stated plainly as roadmap: two-way ERP
  write-back (payloads are produced today; posting them into a live ERP
  is the connector track), bank-file formats (BAI2, MT940, lockbox), a
  formal correction-learning loop, and SOC 2, which is a process
  programme rather than a code feature.
