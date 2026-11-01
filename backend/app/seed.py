"""Seed scenario: a labelled synthetic workspace so the product can be
evaluated end to end. Cases by design: exact, split, PO-won, discount+deduction,
partial, duplicate, unknown payer, no-remittance."""
from domain import Invoice, Payment

def seed_invoices():
    return [
        Invoice("INV-1001", "Apex Manufacturing", "Apex Manufacturing", 12000, po_number="PO-11", age_days=40, due_in_days=-40),
        Invoice("INV-1002", "Apex Manufacturing", "Apex Manufacturing", 8000, po_number="PO-12", age_days=5, due_in_days=-5),
        Invoice("INV-1003", "Apex Manufacturing", "Apex Manufacturing", 20000, po_number="PO-13", age_days=30, due_in_days=-30),
        Invoice("INV-1004", "BluePeak Electronics", "BluePeak Electronics", 100000, po_number="PO-21", discount_rate=0.02, age_days=25, due_in_days=-25),
        Invoice("INV-1005", "BluePeak Electronics", "BluePeak Electronics", 15000, po_number="PO-22", age_days=12, due_in_days=-12),
        Invoice("INV-1006", "Cascade Chemicals", "Cascade Chemicals", 30000, po_number="PO-31", age_days=18, due_in_days=-18),
        Invoice("INV-1007", "Cascade Chemicals", "Cascade Chemicals", 45000, po_number="PO-32", age_days=50, due_in_days=-50),
        Invoice("INV-1008", "Summit Logistics", "Summit Logistics", 22000, po_number="PO-41", age_days=8, due_in_days=6),
    ]

def seed_payments():
    return [
        # split: 12000 + 8000 = 20000, MILP must prefer old INV-1001+INV-1002 over single INV-1003
        Payment("P1", "Apex Manufacturing", 20000, remittance_text="Wire from Apex Manufacturing for INV-1001 and INV-1002"),
        # PO-won: reference wrong in text, PO-13 points to INV-1003
        Payment("P2", "Apex Manufacturing", 20000, references=["PO-13"], remittance_text="Payment ref PO-13 (invoice ref in mail was wrong)"),
        # discount + deduction: 100000 - 2000 - 5000 = 93000
        Payment("P3", "BluePeak Electronics", 93000, claimed_deduction_cents=5000, deduction_reason_raw="shortage on delivery",
                pod_verified_clean=True, remittance_text="BluePeak Electronics wire less 2% discount, less deduction $50 shortage"),
        # partial: pays 10000 of INV-1005 (15000)
        Payment("P4", "BluePeak Electronics", 10000, references=["INV-1005"]),
        # duplicate of P1 fingerprint
        Payment("P5", "Apex Manufacturing", 20000),
        # unknown payer
        Payment("P6", "TransGlobal Trading", 77700),
        # exact single
        Payment("P7", "Cascade Chemicals", 30000, references=["INV-1006"]),
        # no-remittance exact amount for Summit Logistics (amount+payer path)
        Payment("P8", "Summit Logistics", 22000),
    ]

GROUND_TRUTH = {  # payment_id -> set of invoice_ids a correct matcher should select (primary case)
    "P1": {"INV-1001", "INV-1002"}, "P2": {"INV-1003"}, "P3": {"INV-1004"},
    "P7": {"INV-1006"}, "P8": {"INV-1008"},
}
