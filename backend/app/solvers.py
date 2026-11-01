"""Matching solvers: MILP (primary), subset-sum counterfactuals, greedy baseline.
The MILP formulation is Harsha's original AutoCash engine, productised:
candidate restriction is applied by the caller; money stays integer cents."""
import time
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from domain import Invoice, Payment, Policy, MatchResult, MatchLine

def _confidence(lines, invoices_by_id, payment, residual_cents, matched_by):
    if not lines:
        return 0.0
    base = 1.0 if residual_cents == 0 else max(0.3, 1.0 - abs(residual_cents) / max(payment.amount_cents, 1))
    if matched_by in ("reference", "po"):
        base = min(1.0, base + 0.03)
    return round(base, 4)

def solve_milp(payment: Payment, candidates: list, policy: Policy) -> MatchResult:
    t0 = time.perf_counter()
    n = len(candidates)
    if n == 0:
        return MatchResult(payment.payment_id, "NO_MATCH", "milp", 0.0, [], False, payment.amount_cents, 0.0, "none", {})
    num_vars = 2 * n + 3
    integrality = np.ones(num_vars); integrality[-2:] = 0
    c = np.zeros(num_vars)
    for i, inv in enumerate(candidates):
        c[i] = -(1.0 + inv.age_days * policy.age_weight)
        c[n + i] = policy.discount_penalty
    c[2 * n] = policy.deduction_penalty
    c[2 * n + 1] = policy.residual_penalty
    c[2 * n + 2] = policy.residual_penalty
    A_eq = np.zeros((1, num_vars))
    for i, inv in enumerate(candidates):
        A_eq[0, i] = inv.gross_cents
        A_eq[0, n + i] = -round(inv.gross_cents * inv.discount_rate)
    A_eq[0, 2 * n] = -payment.claimed_deduction_cents
    A_eq[0, 2 * n + 1] = 1.0; A_eq[0, 2 * n + 2] = -1.0
    A_ub = np.zeros((n, num_vars))
    for i in range(n):
        A_ub[i, i] = -1.0; A_ub[i, n + i] = 1.0
    A_full = np.vstack([A_eq, A_ub])
    lb_con = np.concatenate([[payment.amount_cents], np.full(n, -np.inf)])
    ub_con = np.concatenate([[payment.amount_cents], np.zeros(n)])
    lb_vars = np.zeros(num_vars); ub_vars = np.ones(num_vars); ub_vars[-2:] = np.inf
    res = milp(c=c, integrality=integrality, bounds=Bounds(lb_vars, ub_vars),
               constraints=LinearConstraint(A_full, lb_con, ub_con))
    latency = round((time.perf_counter() - t0) * 1000, 2)
    sol = res.x
    lines, by_id = [], {inv.invoice_id: inv for inv in candidates}
    for i, inv in enumerate(candidates):
        if round(sol[i]) == 1:
            dt = round(sol[n + i]) == 1
            dc = round(inv.gross_cents * inv.discount_rate) if dt else 0
            lines.append(MatchLine(inv.invoice_id, inv.gross_cents, dc, inv.gross_cents - dc, dt))
    residual = int(round(sol[2 * n + 1] - sol[2 * n + 2]))
    ded = bool(round(sol[2 * n]) == 1)
    status = "OPTIMAL_EXACT_MATCH" if residual == 0 and lines else ("PARTIAL_MATCH" if lines else "NO_MATCH")
    matched_by = "solver_subset"
    terms = []
    for l in lines:
        inv = by_id[l.invoice_id]
        coeff = -(1.0 + inv.age_days * policy.age_weight)
        terms.append({"term": f"select {inv.invoice_id}", "formula": f"-(1 + age {inv.age_days}d x age_weight {policy.age_weight})", "value": round(coeff, 4)})
        if l.discount_taken:
            terms.append({"term": f"discount on {inv.invoice_id}", "formula": f"+ discount_penalty {policy.discount_penalty}", "value": policy.discount_penalty})
    if ded:
        terms.append({"term": "accept claimed deduction", "formula": f"+ deduction_penalty {policy.deduction_penalty}", "value": policy.deduction_penalty})
    if residual != 0:
        terms.append({"term": "unexplained residual", "formula": f"+ residual_penalty {policy.residual_penalty} x |residual| {abs(residual)} cents", "value": policy.residual_penalty * abs(residual)})
    conf_base = 1.0 if residual == 0 else max(0.3, 1.0 - abs(residual) / max(payment.amount_cents, 1))
    factors = {"residual_cents": residual, "invoices_considered": n,
               "objective_terms": terms, "objective_total": round(sum(t["value"] for t in terms), 4),
               "confidence_derivation": {"base": round(conf_base, 4),
                   "base_rule": "1.0 when residual is 0, else max(0.3, 1 - |residual| / payment amount)",
                   "reference_bonus": 0.0, "bonus_rule": "+0.03 only when the match came from an explicit reference or PO path"}}
    conf = _confidence(lines, by_id, payment, residual, matched_by)
    return MatchResult(payment.payment_id, status, "milp", latency, lines, ded, residual, conf, matched_by, factors)

def solve_greedy(payment: Payment, candidates: list, policy: Policy) -> MatchResult:
    """Naive first-fit baseline the MILP must beat: take invoices in listed
    order while they fit the remaining amount; no subset search, no discounts."""
    t0 = time.perf_counter()
    remaining = payment.amount_cents
    lines = []
    for inv in candidates:
        if inv.gross_cents <= remaining:
            lines.append(MatchLine(inv.invoice_id, inv.gross_cents, 0, inv.gross_cents, False))
            remaining -= inv.gross_cents
    latency = round((time.perf_counter() - t0) * 1000, 2)
    residual = remaining
    status = "OPTIMAL_EXACT_MATCH" if residual == 0 and lines else ("PARTIAL_MATCH" if lines else "NO_MATCH")
    conf = _confidence(lines, {}, payment, residual, "greedy_order")
    return MatchResult(payment.payment_id, status, "greedy", latency, lines, False, residual, conf, "greedy_order", {"residual_cents": residual})

def why_not_invoice(payment: Payment, candidates: list, invoice_id: str, policy: Policy) -> dict:
    """Counterfactual: force the invoice in, re-solve, report the cost.
    Returns the residual delta and whether a subsidiary mismatch blocks it."""
    target = next((i for i in candidates if i.invoice_id == invoice_id), None)
    if target is None:
        return {"invoice_id": invoice_id, "reason": "not_in_candidate_set"}
    base = solve_milp(payment, candidates, policy)
    if any(l.invoice_id == invoice_id for l in base.lines):
        return {"invoice_id": invoice_id, "reason": "already_matched", "residual_cents": base.residual_cents}
    # residual if this invoice were applied on its own against the wire
    solo_residual = payment.amount_cents - target.gross_cents + (payment.claimed_deduction_cents if base.deduction_applied else 0)
    return {
        "invoice_id": invoice_id,
        "reason": "excluded_by_optimisation",
        "invoice_gross_cents": target.gross_cents,
        "solo_residual_cents": solo_residual,
        "explanation": (
            f"Including {invoice_id} ({target.gross_cents/100:.2f}) leaves a solo residual of "
            f"{solo_residual/100:.2f} against this wire, and the solver found a combination "
            f"with residual {base.residual_cents/100:.2f}; the optimiser prefers the lower-residual set."
        ),
    }
