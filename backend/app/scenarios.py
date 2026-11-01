"""Use-case library: labelled, self-contained scenario packs.

Each scenario runs in a clean-room in-memory ledger, so running a use case
never pollutes the workspace. Every pack states, in plain language, what it
demonstrates and what a correct run must produce; the API verifies the
actual outcome against those expectations and reports pass or fail per
check - the same honesty standard as the evaluations page.
"""
from domain import Invoice, Payment

def _inv(sid, n, customer, cents, **kw):
    return Invoice(f"{sid}-INV-{n}", customer, customer, cents, **kw)

def _pay(sid, n, payer, cents, **kw):
    return Payment(f"{sid}-P{n}", payer, cents, **kw)

SCENARIOS = [
    {
        "id": "split-exact",
        "title": "Split payment across two invoices",
        "story": "A customer pays $200 in one wire covering two open invoices ($120 + $80), while a single $200 invoice from the same customer sits open as a decoy. A greedy or amount-only matcher grabs the decoy; the MILP optimiser must prefer the pair because the policy ages work oldest first.",
        "shows": "Subset-sum matching under a cash conservation equation, with an age-weighted objective.",
        "build": lambda: (
            [_inv("S1", 1, "Apex Manufacturing", 12000, po_number="PO-11", age_days=40),
             _inv("S1", 2, "Apex Manufacturing", 8000, po_number="PO-12", age_days=5),
             _inv("S1", 3, "Apex Manufacturing", 20000, po_number="PO-13", age_days=30)],
            [_pay("S1", 1, "Apex Manufacturing", 20000, remittance_text="Wire covering INV-1 and INV-2")],
        ),
        "expect": {"S1-P1": {"status": "OPTIMAL_EXACT_MATCH", "auto_posted": True, "invoices": {"S1-INV-1", "S1-INV-2"}}},
    },
    {
        "id": "po-wins",
        "title": "Wrong invoice reference, right purchase order",
        "story": "The remittance names the wrong invoice, but carries purchase order PO-13. Reference matching alone would post against the wrong document; the engine resolves candidates by PO first and posts to the invoice the PO actually belongs to.",
        "shows": "Candidate resolution order: references, then PO, then payer and amount - and why order matters.",
        "build": lambda: (
            [_inv("S2", 1, "Apex Manufacturing", 20000, po_number="PO-13", age_days=30),
             _inv("S2", 2, "Apex Manufacturing", 20000, po_number="PO-14", age_days=10)],
            [_pay("S2", 1, "Apex Manufacturing", 20000, references=["PO-13"], remittance_text="Payment ref PO-13 (invoice ref in mail was wrong)")],
        ),
        "expect": {"S2-P1": {"status": "OPTIMAL_EXACT_MATCH", "auto_posted": True, "invoices": {"S2-INV-1"}}},
    },
    {
        "id": "discount-deduction-dispute",
        "title": "Early-pay discount plus a shortage deduction",
        "story": "A $2,000 invoice with 2 percent early-pay terms is paid at $1,560: the discount taken, plus a $400 shortage deduction. Proof of delivery is clean. The engine must reconcile to zero residual AND judge the deduction: win probability 0.94 on clean POD, expected recovery $331 after the $45 processing cost, above the $100 auto-dispute threshold - so a dispute claim is raised automatically.",
        "shows": "Deduction intelligence: reason classification, win-probability evidence rules, and expected-value dispute decisions.",
        "build": lambda: (
            [_inv("S3", 1, "BluePeak Electronics", 200000, po_number="PO-21", discount_rate=0.02, age_days=25)],
            [_pay("S3", 1, "BluePeak Electronics", 156000, claimed_deduction_cents=40000,
                  deduction_reason_raw="shortage on delivery", pod_verified_clean=True,
                  remittance_text="Wire less 2% discount, less $400 shortage deduction")],
        ),
        "expect": {"S3-P1": {"status": "OPTIMAL_EXACT_MATCH", "auto_posted": True, "invoices": {"S3-INV-1"}, "deduction_action": "AUTO_GENERATE_DISPUTE_CLAIM", "erp_reason_code": "RC-02"}},
    },
    {
        "id": "duplicate-guard",
        "title": "The same wire arrives twice",
        "story": "Bank feeds and lockbox files do resend payments. The identical wire appears twice in one batch. The first posts cleanly; the second must be stopped as a duplicate and routed to a human, never double-posted against other invoices.",
        "shows": "Payment fingerprinting and duplicate defence inside the batch, before any matching happens.",
        "build": lambda: (
            [_inv("S4", 1, "Cascade Chemicals", 30000, po_number="PO-31", age_days=18)],
            [_pay("S4", 1, "Cascade Chemicals", 30000, references=["S4-INV-1"]),
             _pay("S4", 2, "Cascade Chemicals", 30000)],
        ),
        "expect": {"S4-P1": {"status": "OPTIMAL_EXACT_MATCH", "auto_posted": True, "invoices": {"S4-INV-1"}},
                   "exceptions": {"S4-P2": "DUPLICATE_PAYMENT"}},
    },
    {
        "id": "partial-residual",
        "title": "Partial payment with an unexplained residual",
        "story": "A customer pays $100 against a $150 invoice and explains nothing. The engine posts the partial match, quantifies the $50 residual, and raises a review exception with counterfactuals - what else could this cash have been? - instead of silently writing it off or forcing a wrong match.",
        "shows": "Partial matching, residual accounting, and the exception workflow with why-not counterfactuals.",
        "build": lambda: (
            [_inv("S5", 1, "BluePeak Electronics", 15000, po_number="PO-22", age_days=12),
             _inv("S5", 2, "BluePeak Electronics", 5000, po_number="PO-23", age_days=3)],
            [_pay("S5", 1, "BluePeak Electronics", 10000, references=["S5-INV-1"])],
        ),
        "expect": {"S5-P1": {"status": "PARTIAL_MATCH", "auto_posted": False, "invoices": {"S5-INV-1"}, "residual_cents": -5000},
                   "exceptions": {"S5-P1": "UNRESOLVED_RESIDUAL"}},
    },
    {
        "id": "silent-exact",
        "title": "No remittance at all, exact amount",
        "story": "A wire lands with no remittance text and no references - only a payer name and an amount that exactly equals one open invoice for that payer. The engine falls back to payer plus amount resolution and still posts touchlessly, with the matched-by path recorded for audit.",
        "shows": "Graceful degradation of the matching cascade when remittance data is missing entirely.",
        "build": lambda: (
            [_inv("S6", 1, "Summit Logistics", 22000, po_number="PO-41", age_days=8),
             _inv("S6", 2, "Summit Logistics", 9000, po_number="PO-42", age_days=2)],
            [_pay("S6", 1, "Summit Logistics", 22000)],
        ),
        "expect": {"S6-P1": {"status": "OPTIMAL_EXACT_MATCH", "auto_posted": True, "invoices": {"S6-INV-1"}}},
    },
]

def get_scenario(sid):
    for s in SCENARIOS:
        if s["id"] == sid:
            return s
    return None

SCENARIOS += [
    {
        "id": "blind-lockbox-wire",
        "title": "Blind lockbox wire - $1,145,820.00, zero remittance",
        "story": "A seven-figure wire lands from a lockbox file with no remittance text, no references, nothing but the payer name and the amount. Three invoices are open for the payer; only one equals the wire to the cent and no combination of the others can sum to it. The engine must fall back to payer plus exact-amount resolution and still post a million-dollar wire touchlessly - with the matched-by path recorded for audit.",
        "shows": "The bottom rung of the matching cascade at enterprise scale: payer plus amount, with subset-sum proof that no other combination explains the cash.",
        "build": lambda: (
            [_inv("S7", 1, "Continental Foodservice", 25000000, po_number="PO-771", age_days=22),
             _inv("S7", 2, "Continental Foodservice", 114582000, po_number="PO-772", age_days=35),
             _inv("S7", 3, "Continental Foodservice", 48000055, po_number="PO-773", age_days=9)],
            [_pay("S7", 1, "Continental Foodservice", 114582000)],
        ),
        "expect": {"S7-P1": {"status": "OPTIMAL_EXACT_MATCH", "auto_posted": True, "invoices": {"S7-INV-2"}}},
    },
    {
        "id": "corrupted-ocr-remittance",
        "title": "Corrupted OCR remittance - the PO survives",
        "story": "A $482,190.50 wire arrives with a remittance advice mangled by OCR: the invoice references are unreadable garbage. Two open invoices for the payer carry the exact same amount; the older one is the tempting wrong answer an amount-or-age matcher would post. One field survived the scan intact - purchase order PO-8841 - and it belongs to the younger invoice. The engine must let the surviving evidence outrank age and amount.",
        "shows": "Evidence hierarchy under data corruption: PO resolution beats the age-weighted objective when references are destroyed.",
        "build": lambda: (
            [_inv("S8", 1, "MegaMart Retail", 48219050, po_number="PO-8850", age_days=60),
             _inv("S8", 2, "MegaMart Retail", 48219050, po_number="PO-8841", age_days=15)],
            [_pay("S8", 1, "MegaMart Retail", 48219050, references=["PO-8841"],
                  remittance_text="OCR scan: 1NV-88O2 / 1NV-88S1 illegible - PO-8841 legible")],
        ),
        "expect": {"S8-P1": {"status": "OPTIMAL_EXACT_MATCH", "auto_posted": True, "invoices": {"S8-INV-2"}}},
    },
    {
        "id": "promo-deduction-spike",
        "title": "Promotional deduction spike - $9,000 claimed on a $312,400 invoice",
        "story": "A retailer pays $303,400.00 against a $312,400.00 invoice and claims a $9,000 promotional allowance deduction - twenty standard deviations above this payer's deduction history in the demo profile (z = 20.0). Proof of delivery is clean. The engine reconciles the match exactly, flags the claim as an anomalous spike, classifies it RC-07 Promotional Allowance, and runs the dispute arithmetic: 0.94 x $9,000 - $45 = $8,415 expected recovery, far above the $100 threshold, so the dispute claim generates itself.",
        "shows": "Anomaly detection (z-score) and expected-value dispute automation on a claim large enough to matter.",
        "build": lambda: (
            [_inv("S9", 1, "ShopLine Retail", 31240000, po_number="PO-991", age_days=28)],
            [_pay("S9", 1, "ShopLine Retail", 30340000, claimed_deduction_cents=900000,
                  deduction_reason_raw="promotional allowance per Q3 deal sheet", pod_verified_clean=True,
                  remittance_text="Wire less promotional allowance deduction $9,000")],
        ),
        "expect": {"S9-P1": {"status": "OPTIMAL_EXACT_MATCH", "auto_posted": True, "invoices": {"S9-INV-1"},
                             "deduction_action": "AUTO_GENERATE_DISPUTE_CLAIM", "erp_reason_code": "RC-07", "spike": True}},
    },
]

SCENARIOS.append({
    "id": "fuzzy-ocr-evidence",
    "title": "Mangled evidence - OCR reference and a fuzzy payer name",
    "story": "The wire's remittance was scanned and the purchase order came out as P0-51 (a zero where the letter O belongs) instead of PO-51; the payer name on the wire reads 'APEX MANUFACTURING INC.' while the ledger customer is 'Apex Manufacturing'. Exact matching fails twice over. The engine retries references under OCR confusion normalisation (0 read as O), recovers PO-51 and posts to its invoice - and had the reference been destroyed entirely, a Jaro-Winkler fuzzy payer match (threshold 0.88) is the labelled fallback.",
    "shows": "Evidence recovery: OCR-normalised references and fuzzy entity resolution as labelled, auditable fallback rungs - never silent guesses.",
    "build": lambda: (
        [_inv("S10", 1, "Apex Manufacturing", 75000, po_number="PO-51", age_days=20),
         _inv("S10", 2, "Apex Manufacturing", 41000, po_number="PO-52", age_days=44)],
        [_pay("S10", 1, "APEX MANUFACTURING INC.", 75000, references=["P0-51"], remittance_text="Scanned remittance: P0-51 (OCR)")],
    ),
    "expect": {"S10-P1": {"status": "OPTIMAL_EXACT_MATCH", "auto_posted": True, "invoices": {"S10-INV-1"}}},
})
