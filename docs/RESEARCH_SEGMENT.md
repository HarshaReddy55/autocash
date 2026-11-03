# AutoCash - Market and Segment Research
AutoCash product pack, document 2 of 8. Previous: Product Requirements
Document. Next: Architecture and System Design.
Compiled 31 Oct 2026 from vendor pages and analyst coverage; the
AutoCash mapping was updated 2 Nov 2026 and the format revised 3 Nov
2026. All market figures below are vendor claims or analyst findings
from those sources. None are independently verified by us, and none
are AutoCash results.

## 1. Executive summary
Cash application vendors compete on a headline auto-match rate, and
the headline is not the measured reality. Independent analyst
benchmarking (The Hackett Group, 2025) puts the median auto-match rate
near 70 percent, with the top third of finance organisations above 80
percent, while vendors in the same category advertise 85 to 99
percent. Differentiation has therefore shifted away from the headline
rate, which has plateaued, toward the unmatched tail: how exceptions
are explained, valued and resolved, and whether every decision can be
audited afterwards. That tail is where AutoCash is built to compete.

## 2. Target market definition
The entry segment is mid-market finance teams whose AR analysts still
match a material share of payments by hand: product, distribution and
services companies large enough to receive split wires, deduction-heavy
payments and multi-format remittance, and small enough that a
multi-quarter platform implementation is a hard sell. The operational
realities that define the segment:

- Split information channels: funds arrive by wire or lockbox while
  remittance detail arrives separately, as email, scanned documents or
  portal messages, often naming purchase orders instead of invoices.
- Complex buyer behaviour: lump-sum wires covering many invoices,
  early-payment discounts taken after their window has closed, and
  unilateral deductions for alleged shortages or damage.
- Exception economics: the payments that match cleanly are cheap for
  any system; the tail consumes the analyst hours, and at month end it
  sits as unapplied cash distorting collections and forecasting.

## 3. Players and wedges
- HighRadius: category definer, full Office-of-the-CFO platform; cash
  application marketed as 90 percent plus straight-through processing
  via 13 AI agents (vendor claim); LiveCube no-code data layer;
  enterprise, custom priced, implementation heavy; pricing moved to an
  outcome-based model in 2026.
- BlackLine: control and close wedge; Verity AI (Remit, Match,
  Collect), Vera supervisor agent; claims about 85 percent auto-match;
  ISO/IEC 42001 AI governance.
- Esker: document intelligence wedge; deep-learning first-time
  recognition of unseen remittance layouts, teaching mode, learns from
  corrections.
- Quadient AR (formerly YayPay): mid-market full AR; ML suggests the
  customer for unidentified payments, for human approval.
- Billtrust: payments network wedge (Business Payments Network and
  Digital Lockbox); claims top-quartile 99.6 percent match, 40
  exceptions per analyst-hour.
- Emagia: AI-native breadth, six autonomous modules, Gia studio;
  claims 95 percent plus auto-match, 97 percent plus touchless
  capture.
- Gaviti: collections execution only (prioritisation, adaptive
  dunning).
- Tesorio: predictive cash intelligence (per-invoice payment-date
  prediction).
- Also: Serrala (SAP-embedded), Versapay (portal-led capture).

## 4. The six core cash application failure modes
AutoCash's ten scenario packs and its flagship demo dataset are built
around the failure modes that break simpler matching. Each mode below
is exercised by a named scenario pack or by the demo case, and the
resolution column names the mechanism, not a promise.

| Failure mode | Real-world scenario | Why legacy handling fails | AutoCash resolution |
| :--- | :--- | :--- | :--- |
| 1. Multi-invoice split wire | One lump-sum wire covers several open invoices and lists no per-invoice amounts | Subset selection over a customer's open ledger is a combinatorial search; rules engines guess or give up | The MILP solver finds the exact-cent set under the cash conservation equation, and the ambiguity rule holds the match for a person if a second exact set exists (scenario pack: split-exact) |
| 2. PO-only reference | The buyer's system prints only a purchase order number on the wire memo | Lookup keyed strictly on invoice numbers finds nothing and dumps the wire into suspense | The Linking Agent resolves purchase order numbers against the open ledger before amount matching (scenario pack: po-wins) |
| 3. OCR character corruption | A scanned remittance swaps characters (0 for O, 1 for I) in an invoice reference | Exact string lookup misses the invoice and raises a false exception | Edit-distance-1 repair, verified against the open ledger for that customer; repaired evidence ranks below stated references in processing order (scenario pack: corrupted-ocr-remittance) |
| 4. Unearned discount with a shortage claim | A buyer takes an early-payment discount after its window closed and deducts again for alleged damage | The net wire matches neither gross nor discounted totals, and the difference is often written off to clear the queue | The solver isolates the discount and claim cents; the Deduction Agent classifies them (RC-12 Unearned Discount, RC-02 Damaged/Shortage Claim), checks proof of delivery, and values the dispute by expected recovery (scenario pack: discount-deduction-dispute) |
| 5. Duplicate bank wire | The same wire is transmitted twice | The second wire clears unrelated invoices by coincidence or sits unapplied | A SHA-256 fingerprint over payer, amount and currency blocks the repeat before matching; it is recorded as an exception only (scenario pack: duplicate-guard) |
| 6. Unrecognised payer | A parent company or payment processor wires funds for a billed subsidiary | Name lookup finds no open invoices for that payer | Fuzzy and whole-ledger evidence is capped at 0.78 confidence, so the best case is a proposal for a person, never an auto-post; if nothing explains the wire, the engine issues a reasoned refusal (scenario pack: fuzzy-ocr-evidence; the demo case carries one unknown-payer refusal) |

The remaining packs cover partial payments with residuals, silent
exact matches on plain wires, and blind lockbox wires with no
remittance at all. All ten packs pass their checks through the real
run path.

## 5. 2026 table stakes (per the brief)
Omnichannel ingestion (email, EDI 820/823, BAI2, MT940/CAMT, lockbox,
AP portals); two-way ERP connectors (SAP, Oracle, NetSuite, Dynamics);
multi-reference matching with correction learning; deductions as a
first-class workflow (reason codes, tolerance, validity, dispute
packets); coupled collections and forecasting; an agent control plane
with per-step confidence and human-in-the-loop queues; evaluation and
governance (reproducible, auditable decisions); SOC 2 / ISO posture,
immutable audit, RBAC, maker-checker.

## 6. White space (the brief's findings)
1. The exception tail, productised: counterfactual explanations, a
   computed next-best-action, and a public, reproducible evaluation
   harness on labelled data. Open evaluation is unclaimed territory.
2. Provable correctness over probabilistic matching: a hard-constraint
   optimiser (MILP, cash-conservation equality) that proves a posting
   set is residual-optimal and shows the proof.
3. Mid-market, self-serve, fast deployment: API-first, CSV onboarding
   in days, transparent pricing, no ERP modification.
4. Governed policy as configuration: solver weights and thresholds as
   versioned, audited configuration, owned by the customer. No AR
   vendor owns this today.
5. Deployment model: bring-your-own-cloud, open APIs.
6. Regional depth (inference, flagged as such in the brief): UPI and
   NEFT reference formats, Tally, Zoho and local ERPs, GST artefacts,
   all absent from US-centric leaders.

## 7. Pricing signals (second research pass, 31 Oct 2026, sourced)
- Almost nobody in this segment publishes pricing (a 2026 comparison
  of nine leading vendors found none publishing prices; all require a
  sales cycle).
- HighRadius: no rate card; the public model is outcome-based (vendor
  claim: no implementation or subscription fee until go-live, then
  fees tied to agreed success criteria). Third-party estimates, not
  vendor-published, put enterprise deployments at roughly $200k to
  $500k per year.
- Billtrust: quote-only; third-party estimates of roughly $20k to $60k
  per year base for mid-market, processing extra.
- BlackLine, Esker, Emagia, Quadient AR, Gaviti: all quote-based,
  sized on volume, entities, modules and users. No public per-payment
  rate found.
- Category pattern: per-seat pricing is not standard; lighter
  mid-market subscriptions run broadly $1,000 to $5,000 per month
  (third-party estimates).
- Implementation pain (reviewer-reported, G2): HighRadius AR averages
  about 8 months to implement and 16 months to ROI; configuration
  changes can require vendor consulting at extra cost. Practitioner
  analysis names black-box audit risk as a core limitation of AI cash
  application products.

## 8. How AutoCash maps today (honest)
- Owns white space 1, 2 and 4. Counterfactual why-not explanations on
  every non-match; a live, labelled evaluation endpoint any reviewer
  can run; a MILP solver that re-verifies its own answers in exact
  cents and shows its derivation; tenant policy as versioned, audited
  configuration.
- Aligned with 3 and 5. CSV and file onboarding is live (including OCR
  of PDF and image remittances), and the product ships as one container
  image that runs on the customer's own cloud account.
- Built since this brief was first compiled: the SAP posting pack
  (balanced DZ journals, the full BAPI_ACC_DOCUMENT_POST payload and
  the ASC 606 reserve journal) and the outbound mail hub, which turns
  run outcomes into dispute claims, inquiries, confirmations and
  dunning.
- Gaps against table stakes, stated plainly as roadmap: two-way ERP
  write-back (payloads are produced today; posting them into a live
  ERP is the connector track), bank-file formats (BAI2, MT940,
  lockbox), a formal correction-learning loop, and SOC 2, which is a
  process programme rather than a code feature.

Version 3.0 | 3 Nov 2026 | Owner: C. Harsha Vardhana Reddy
