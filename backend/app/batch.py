"""Batch reconciliation: many payments against the open ledger.
Candidate restriction order: explicit references (invoice/PO) -> payer customer
(alias-aware) -> subsidiary. Matched invoices are consumed so two payments
cannot claim the same invoice (ledger consistency across the batch)."""
import time, uuid, json
from dataclasses import asdict
from datetime import datetime, timezone
from domain import Policy
from solvers import solve_milp, solve_greedy
from anomaly import deduction_intelligence, payment_fingerprint

def _now(): return datetime.now(timezone.utc).isoformat()

def resolve_candidates(payment, open_invoices, aliases):
    payer = (aliases.get(payment.payer_raw.strip().lower()) or payment.payer_raw).strip().lower()
    by_ref = []
    for inv in open_invoices:
        if inv.invoice_id in payment.references or (inv.po_number and inv.po_number in payment.references):
            by_ref.append(inv)
    if by_ref:
        return by_ref, ("po" if any(i.po_number in payment.references for i in by_ref) else "reference")
    # OCR rung: references mangled by scanning (1NV for INV, PO-8O for PO-80)
    # are normalised and retried before any name-based fallback.
    from fuzzy import ocr_variants
    expanded = set()
    for r in payment.references: expanded |= ocr_variants(r)
    if expanded != set(payment.references):
        ocr_hits = [inv for inv in open_invoices
                    if inv.invoice_id in expanded or (inv.po_number and inv.po_number in expanded)]
        if ocr_hits:
            return ocr_hits, "ocr_reference"
    same_cust = [i for i in open_invoices if i.customer.strip().lower() == payer]
    if same_cust:
        return same_cust, "amount_payer"
    # Fuzzy rung: payer name as printed on the wire vs ledger customer names
    # (Jaro-Winkler >= 0.88), labelled so the match stays auditable.
    from fuzzy import best_fuzzy_customer
    customers = sorted({i.customer for i in open_invoices})
    best, _score = best_fuzzy_customer(payment.payer_raw, customers)
    if best:
        return [i for i in open_invoices if i.customer == best], "fuzzy_payer"
    return open_invoices, "all_ledger"

def run_batch(repo, payments, policy: Policy, idempotency_key, actor="system", on_event=None):
    ev = on_event or (lambda e: None)
    existing = repo.find_run_by_idempotency(idempotency_key)
    if existing:
        return {"run_id": existing[0], "status": existing[1], "idempotent_replay": True}
    run_id = "run_" + uuid.uuid4().hex[:12]
    repo.create_run(run_id, idempotency_key, "batch_reconciliation", json.dumps(asdict(policy)), _now())
    ev({"type": "batch_start", "run_id": run_id, "payments": len(payments)})
    aliases = {}
    try:
        rows = repo.conn.execute("SELECT raw_name, customer FROM aliases").fetchall()
        aliases = {r[0]: r[1] for r in rows}
    except Exception:
        pass
    open_invoices = repo.open_invoices()
    seen_fingerprints = {}
    results, exceptions = [], []
    t0 = time.perf_counter()
    for pay in payments:
        ev({"type": "payment_start", "payment_id": pay.payment_id, "payer": pay.payer_raw,
            "amount_cents": pay.amount_cents})
        fp = payment_fingerprint(pay)
        if fp in seen_fingerprints:
            ex = {"payment_id": pay.payment_id, "kind": "DUPLICATE_PAYMENT", "severity": "HIGH",
                  "recommended_action": "Hold and verify with payer before posting",
                  "detail": {"duplicate_of": seen_fingerprints[fp]}}
            repo.add_exception(run_id, pay.payment_id, ex["kind"], ex["severity"], ex["recommended_action"], ex["detail"])
            exceptions.append(ex)
            ev({"type": "decision", "payment_id": pay.payment_id, "decision": "EXCEPTION",
                "reason": "Duplicate payment fingerprint - held before matching, never posted twice."})
            continue
        seen_fingerprints[fp] = pay.payment_id
        cands, matched_by = resolve_candidates(pay, open_invoices, aliases)
        ev({"type": "resolved", "payment_id": pay.payment_id, "matched_by": matched_by,
            "candidates": len(cands)})
        res = solve_milp(pay, cands, policy)
        ev({"type": "solved", "payment_id": pay.payment_id, "status": res.status,
            "invoices": [l.invoice_id for l in res.lines], "residual_cents": res.residual_cents,
            "confidence": res.confidence, "latency_ms": res.latency_ms})
        res.matched_by = matched_by if res.lines else res.matched_by
        status = res.status
        match_id = "m_" + uuid.uuid4().hex[:10]
        auto = res.confidence >= policy.automation_threshold and status == "OPTIMAL_EXACT_MATCH"
        decision_reason = None
        if auto and pay.amount_cents > policy.maker_checker_threshold_cents:
            auto = False
            decision_reason = (f"Maker-checker: this payment is ${pay.amount_cents/100:,.2f}, above the "
                               f"${policy.maker_checker_threshold_cents/100:,.2f} policy threshold - a second "
                               "approver must sign before it posts.")
        if decision_reason is None:
            decision_reason = ("Exact match, confidence "
                               f"{res.confidence:.2f} at or above the {policy.automation_threshold:.2f} threshold - posted by policy."
                               ) if auto else (f"Not an exact match ({status}, residual ${res.residual_cents/100:,.2f}) - held for analyst review.")
        _greedy = solve_greedy(pay, cands, policy)
        _net = sum(l.net_cents for l in res.lines)
        _ded_amt = pay.claimed_deduction_cents if res.deduction_applied else 0
        _deriv = {"equation": {"net_applied_cents": _net, "deduction_applied_cents": _ded_amt,
                               "residual_cents": res.residual_cents, "payment_cents": pay.amount_cents,
                               "balances": (_net - _ded_amt + res.residual_cents) == pay.amount_cents,
                               "reading": "net applied - deduction accepted + residual = payment received"},
                  "objective_terms": res.factors.get("objective_terms", []),
                  "objective_total": res.factors.get("objective_total"),
                  "confidence_derivation": res.factors.get("confidence_derivation"),
                  "candidates_considered": res.factors.get("invoices_considered"),
                  "greedy_comparison": {"invoices": [l.invoice_id for l in _greedy.lines],
                                        "residual_cents": _greedy.residual_cents, "status": _greedy.status,
                                        "reading": "what the first-fit greedy baseline would have done with the same candidates"}}
        repo.add_match(match_id, run_id, pay.payment_id,
                       "AUTO_POSTED" if auto else "PROPOSED", res.solver, res.residual_cents,
                       res.confidence, {"lines": [asdict(l) for l in res.lines], "deduction_applied": res.deduction_applied,
                                        "matched_by": res.matched_by, "latency_ms": res.latency_ms,
                                        "decision_reason": decision_reason,
                                        "derivation": _deriv})
        if res.lines:
            used = {l.invoice_id for l in res.lines}
            open_invoices = [i for i in open_invoices if i.invoice_id not in used]
        if status != "OPTIMAL_EXACT_MATCH":
            ex = {"payment_id": pay.payment_id, "kind": "UNRESOLVED_RESIDUAL" if res.lines else "NO_MATCH",
                  "severity": "HIGH" if not res.lines else "MEDIUM",
                  "recommended_action": "Review counterfactuals and approve or reassign",
                  "detail": {"residual_cents": res.residual_cents}}
            repo.add_exception(run_id, pay.payment_id, ex["kind"], ex["severity"], ex["recommended_action"], ex["detail"])
            exceptions.append(ex)
        ded = deduction_intelligence(pay, 100000, 40000, policy) if pay.claimed_deduction_cents else None
        if ded:
            ev({"type": "deduction", "payment_id": pay.payment_id,
                "decision": ded.get("autonomous_action"), "reason_code": ded.get("assigned_erp_reason_code"),
                "z_score": ded.get("z_score"), "expected_recovery": ded.get("expected_recovery_value_usd")})
        greedy = solve_greedy(pay, cands, policy)
        net_sum = sum(l.net_cents for l in res.lines)
        ded_applied = pay.claimed_deduction_cents if res.deduction_applied else 0
        derivation = {
            "equation": {"net_applied_cents": net_sum, "deduction_applied_cents": ded_applied,
                         "residual_cents": res.residual_cents, "payment_cents": pay.amount_cents,
                         "balances": (net_sum - ded_applied + res.residual_cents) == pay.amount_cents,
                         "reading": "net applied - deduction accepted + residual = payment received"},
            "objective_terms": res.factors.get("objective_terms", []),
            "objective_total": res.factors.get("objective_total"),
            "confidence_derivation": res.factors.get("confidence_derivation"),
            "candidates_considered": res.factors.get("invoices_considered"),
            "greedy_comparison": {"invoices": [l.invoice_id for l in greedy.lines],
                                  "residual_cents": greedy.residual_cents, "status": greedy.status,
                                  "reading": "what the first-fit greedy baseline would have done with the same candidates"}}
        ev({"type": "decision", "payment_id": pay.payment_id,
            "decision": "AUTO_POSTED" if auto else "PROPOSED", "reason": decision_reason})
        results.append({"payment_id": pay.payment_id, "status": status, "auto_posted": auto,
                        "decision_reason": decision_reason,
                        "residual_cents": res.residual_cents, "confidence": res.confidence,
                        "matched_by": res.matched_by, "lines": [asdict(l) for l in res.lines],
                        "deduction": ded, "derivation": derivation})
    total_ms = round((time.perf_counter() - t0) * 1000, 2)
    repo.add_step(run_id, "BatchReconciler", "COMPLETED", total_ms,
                  {"payments": len(payments), "exceptions": len(exceptions)}, None)
    auto_count = sum(1 for r in results if r["auto_posted"])
    repo.finish_run(run_id, "COMPLETED", _now())
    repo.audit(actor, "batch_run_completed", "run", run_id,
               {"payments": len(payments), "auto_posted": auto_count}, _now())
    ev({"type": "batch_done", "run_id": run_id, "payments": len(payments),
        "auto_posted": auto_count, "exceptions": len(exceptions), "ms": total_ms})
    return {"run_id": run_id, "status": "COMPLETED", "payments": len(payments),
            "auto_posted": auto_count,
            "touchless_rate": round(auto_count / max(len(payments), 1), 4),
            "results": results, "exceptions": exceptions}
