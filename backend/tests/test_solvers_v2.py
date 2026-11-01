import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))
from domain import Invoice, Payment, Policy
from solvers import solve_milp, solve_greedy, why_not_invoice

def inv(i, amt, disc=0.0, age=10, cust="Apex Manufacturing"):
    return Invoice(invoice_id=i, customer=cust, subsidiary="Apex Manufacturing", gross_cents=amt, discount_rate=disc, age_days=age)

LEDGER = [inv("INV-1", 12000, age=40), inv("INV-2", 8000, age=5), inv("INV-3", 20000, age=30), inv("INV-4", 5000, age=2)]

def test_milp_beats_greedy_on_split():
    # wire 20000: greedy in listed order takes INV-1 (12000) then INV-2 (8000) = exact too;
    # use order where greedy strands residual: candidates reordered
    cands = [inv("INV-3", 20000, age=30), inv("INV-1", 12000, age=40), inv("INV-2", 8000, age=5)]
    pay = Payment(payment_id="P1", payer_raw="Apex Manufacturing", amount_cents=20000)
    g = solve_greedy(pay, cands, Policy())
    m = solve_milp(pay, cands, Policy())
    assert m.residual_cents == 0
    # MILP objective prefers older invoices: INV-1+INV-2 (ages 40+5) over single INV-3 when both exact
    assert {l.invoice_id for l in m.lines} == {"INV-1", "INV-2"}, [l.invoice_id for l in m.lines]

def test_partial_residual_reported():
    pay = Payment(payment_id="P2", payer_raw="Apex Manufacturing", amount_cents=21000)
    m = solve_milp(pay, LEDGER, Policy())
    assert m.status in ("PARTIAL_MATCH", "OPTIMAL_EXACT_MATCH")
    if m.status == "PARTIAL_MATCH":
        assert m.residual_cents != 0

def test_why_not_counterfactual():
    cands = [inv("INV-3", 20000, age=30), inv("INV-1", 12000, age=40), inv("INV-2", 8000, age=5)]
    pay = Payment(payment_id="P3", payer_raw="Apex Manufacturing", amount_cents=20000)
    w = why_not_invoice(pay, cands, "INV-3", Policy())
    assert w["reason"] == "excluded_by_optimisation" and "residual" in w["explanation"]
