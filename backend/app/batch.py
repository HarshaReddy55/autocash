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

def _usd(cents):
    return f"${cents/100:,.2f}"

def _enumerate_subsets(cands, target_cents):
    """Check every combination of the candidate invoices against the wire.
    Only honest when plain gross arithmetic governs (no discounts, no
    deduction in play). Returns (exact_sets, total_combinations,
    close_calls) or (None, None, []) when enumeration is not valid or the
    candidate list is too large to check completely."""
    n = len(cands)
    if n == 0 or n > 18:
        return None, None, []
    if any(c.discount_rate for c in cands):
        return None, None, []
    amounts = [c.gross_cents for c in cands]
    exact, near = [], []
    def dfs(i, chosen, s):
        if i == n or s > target_cents:
            return
        dfs(i + 1, chosen, s)
        # A subset is recorded exactly once: at the step where its last
        # (highest-index) member joins. Deeper nodes only extend it.
        ns = s + amounts[i]
        nch = chosen + [i]
        if ns == target_cents:
            exact.append(tuple(nch))
        elif abs(ns - target_cents) <= 100000:
            near.append((tuple(nch), ns))
        dfs(i + 1, nch, ns)
    dfs(0, [], 0)
    near.sort(key=lambda x: abs(target_cents - x[1]))
    close = []
    for idxs, s in near[:3]:
        ids = " + ".join(cands[i].invoice_id for i in idxs)
        diff = target_cents - s
        side = f"{_usd(abs(diff))} short of the wire" if diff > 0 else f"{_usd(abs(diff))} over the wire"
        close.append({"invoices": [cands[i].invoice_id for i in idxs], "sum_cents": s, "text": f"{ids} adds up to {_usd(s)} - {side}."})
    return exact, (2 ** n) - 1, close

def _reasoning(pay, cands, matched_by, res, ded, auto, maker_checker, total_open, policy):
    """The decision explained step by step, from the run's own numbers:
    what evidence was used, how the list narrowed, what was tested, why the
    losers lost, and why the decision came out as it did."""
    steps = []
    refs = [r for r in (pay.references or [])]
    if matched_by == "reference":
        steps.append(f"The wire named {', '.join(refs)}. The search started with exactly those invoices - a named reference beats every other kind of evidence.")
    elif matched_by == "po":
        steps.append(f"The wire named purchase order {', '.join(refs)}. The search started with the invoices raised against that PO.")
    elif matched_by == "ocr_reference":
        steps.append("The remittance arrived as a scanned document and the reference came out mangled. The Capture Agent repaired the likely scanning errors (0 read as O, 1 read as I) and the repaired reference found the invoice.")
    elif matched_by == "fuzzy_payer":
        steps.append("The payer name on the wire did not match any customer name exactly. It was close to one customer in the ledger, so that customer's open invoices were used - and the match record says so, so a person can audit the guess.")
    elif matched_by == "all_ledger":
        steps.append("Nothing on this wire matched anything: no usable reference, no PO, no known payer name. Every open invoice had to be considered.")
    elif not (pay.remittance_text or "").strip():
        steps.append("No remittance came with this wire - no invoice numbers, no purchase order, nothing but the payer name and the amount.")
    else:
        steps.append("The remittance named no invoice or purchase order that exists in the ledger, so the search fell back to the payer's own open invoices.")
    if matched_by == "all_ledger":
        steps.append(f"All {total_open} open invoices were in scope for this payment.")
    else:
        steps.append(f"The list narrowed to {len(cands)} open {'invoice' if len(cands) == 1 else 'invoices'} for this payer, out of {total_open} open in the workspace. The solver never searches the whole ledger when the evidence points somewhere first.")
    plain = (not pay.claimed_deduction_cents) and not res.deduction_applied
    exact_sets, combos, close_calls = (_enumerate_subsets(cands, pay.amount_cents) if plain else (None, None, []))
    chosen = {l.invoice_id for l in res.lines}
    if res.status == "OPTIMAL_EXACT_MATCH":
        if exact_sets is not None:
            if len(exact_sets) == 1:
                steps.append(f"Every combination of those invoices was checked ({combos} in total). Exactly one set adds up to the wire to the cent - the set picked below. That is a proof, not a guess: no other combination can explain this cash.")
            else:
                steps.append(f"Every combination of those invoices was checked ({combos} in total). {len(exact_sets)} sets add up to the wire exactly; policy picked the one below because it prefers the oldest invoices.")
        else:
            steps.append("The MILP solver searched these invoices for a set that satisfies the cash conservation equation - money in must equal money applied, to the cent - and found exactly the set below.")
    elif res.lines:
        steps.append(f"No combination of the candidate invoices adds up to the wire exactly. The best set leaves {_usd(abs(res.residual_cents))} unexplained, so the match is only a proposal.")
    else:
        steps.append("No combination of the candidate invoices adds up to this wire, and no single invoice comes close enough to propose. Nothing was posted.")
    if ded:
        act = {"AUTO_GENERATE_DISPUTE_CLAIM": "raise a dispute claim on its own",
               "WRITE_OFF_TOLERANCE": "write it off - it sits inside the small-amount tolerance, so chasing it would cost more than it returns",
               "ROUTE_TO_ANALYST": "hand it to an analyst - the evidence does not settle it"}.get(ded.get("autonomous_action"), "decide as recorded below")
        steps.append(f"The payer also claimed a deduction of {_usd(pay.claimed_deduction_cents)} ({pay.deduction_reason_raw or 'no reason given'}). The Deduction Agent classified it {ded.get('classification', {}).get('label', '')} ({ded.get('assigned_erp_reason_code', '')}) and decided to {act}. The full deduction working is in the panel below.")
    if auto:
        steps.append(f"Decision: posted on its own. The set is exact and the confidence rule passed ({res.confidence:.2f} against the {policy.automation_threshold:.2f} bar in policy), so no person had to touch this payment.")
    elif maker_checker:
        steps.append(f"Decision: held for a second person. The match itself is exact, but this wire is {_usd(pay.amount_cents)}, above the {_usd(policy.maker_checker_threshold_cents)} hold limit in this workspace's policy, so an approver signs it in Approvals before it posts.")
    elif res.status == "OPTIMAL_EXACT_MATCH":
        steps.append("Decision: proposed, not posted. The set is exact but the confidence rule did not pass, so a person confirms it in Approvals.")
    else:
        steps.append("Decision: left for an analyst in Approvals, with the unexplained amount shown as an exception. The platform would rather stop and show its working than post cash it cannot explain.")
    rejections = []
    if res.status == "OPTIMAL_EXACT_MATCH" and len(cands) > len(chosen):
        losers = [c for c in cands if c.invoice_id not in chosen]
        losers.sort(key=lambda c: abs(pay.amount_cents - c.gross_cents))
        for c in losers[:8]:
            if c.gross_cents > pay.amount_cents:
                text = f"{c.invoice_id} is {_usd(c.gross_cents)} - more than the whole wire ({_usd(pay.amount_cents)}), so it cannot be part of any set that adds up to the wire."
            elif exact_sets is not None:
                text = f"{c.invoice_id} is {_usd(c.gross_cents)}. On its own it leaves {_usd(pay.amount_cents - c.gross_cents)} of the wire unexplained, and every combination that includes it was checked - none adds up to the wire exactly."
            else:
                text = f"{c.invoice_id} is {_usd(c.gross_cents)}. On its own it leaves {_usd(pay.amount_cents - c.gross_cents)} of the wire unexplained, and the solver's set below balances to the cent without it."
            rejections.append({"invoice_id": c.invoice_id, "amount_cents": c.gross_cents, "text": text})
        if len(losers) > 8:
            rejections.append({"invoice_id": "", "amount_cents": 0,
                               "text": f"Plus {len(losers) - 8} more open invoice(s) for this payer, each checked and rejected the same way."})
    return {"steps": steps, "rejections": rejections, "close_calls": close_calls,
            "combinations_checked": combos, "exact_sets_found": (len(exact_sets) if exact_sets is not None else None)}

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
    # Per-agent stage accounting: the Run view's agent pipeline and its
    # payload inspector read these steps, so every figure in them is
    # measured here, in the engine, not reconstructed in the UI.
    stage_ms = {"capture": 0.0, "linking": 0.0, "matching": 0.0, "deduction": 0.0, "policy": 0.0}
    rungs, ded_actions = {}, {}
    stats = {"duplicates": 0, "candidates_total": 0, "exact": 0, "milp_ms": 0.0,
             "greedy_differs": 0, "claims": 0, "held": 0}
    t0 = time.perf_counter()
    for pay in payments:
        ev({"type": "payment_start", "payment_id": pay.payment_id, "payer": pay.payer_raw,
            "amount_cents": pay.amount_cents})
        _tc = time.perf_counter()
        fp = payment_fingerprint(pay)
        stage_ms["capture"] += (time.perf_counter() - _tc) * 1000
        if fp in seen_fingerprints:
            stats["duplicates"] += 1
            ex = {"payment_id": pay.payment_id, "kind": "DUPLICATE_PAYMENT", "severity": "HIGH",
                  "recommended_action": "Hold and verify with payer before posting",
                  "detail": {"duplicate_of": seen_fingerprints[fp],
                             "payer": pay.payer_raw, "amount_cents": pay.amount_cents}}
            repo.add_exception(run_id, pay.payment_id, ex["kind"], ex["severity"], ex["recommended_action"], ex["detail"])
            exceptions.append(ex)
            ev({"type": "decision", "payment_id": pay.payment_id, "decision": "EXCEPTION",
                "reason": "Duplicate payment fingerprint - held before matching, never posted twice."})
            continue
        seen_fingerprints[fp] = pay.payment_id
        total_open = len(open_invoices)
        _tl = time.perf_counter()
        cands, matched_by = resolve_candidates(pay, open_invoices, aliases)
        stage_ms["linking"] += (time.perf_counter() - _tl) * 1000
        rungs[matched_by] = rungs.get(matched_by, 0) + 1
        stats["candidates_total"] += len(cands)
        ev({"type": "resolved", "payment_id": pay.payment_id, "matched_by": matched_by,
            "candidates": len(cands)})
        _tm = time.perf_counter()
        res = solve_milp(pay, cands, policy)
        stage_ms["matching"] += (time.perf_counter() - _tm) * 1000
        stats["milp_ms"] += res.latency_ms or 0.0
        if res.status == "OPTIMAL_EXACT_MATCH":
            stats["exact"] += 1
        ev({"type": "solved", "payment_id": pay.payment_id, "status": res.status,
            "invoices": [l.invoice_id for l in res.lines], "residual_cents": res.residual_cents,
            "confidence": res.confidence, "latency_ms": res.latency_ms})
        res.matched_by = matched_by if res.lines else res.matched_by
        status = res.status
        match_id = "m_" + uuid.uuid4().hex[:10]
        _tp = time.perf_counter()
        auto = res.confidence >= policy.automation_threshold and status == "OPTIMAL_EXACT_MATCH"
        decision_reason = None
        maker_checker = False
        if auto and pay.amount_cents > policy.maker_checker_threshold_cents:
            auto = False
            maker_checker = True
            stats["held"] += 1
            decision_reason = (f"Maker-checker: this payment is ${pay.amount_cents/100:,.2f}, above the "
                               f"${policy.maker_checker_threshold_cents/100:,.2f} policy threshold - a second "
                               "approver must sign before it posts.")
        if decision_reason is None:
            decision_reason = ("Exact match, confidence "
                               f"{res.confidence:.2f} at or above the {policy.automation_threshold:.2f} threshold - posted by policy."
                               ) if auto else (f"Not an exact match ({status}, residual ${res.residual_cents/100:,.2f}) - held for analyst review.")
        stage_ms["policy"] += (time.perf_counter() - _tp) * 1000
        _greedy = solve_greedy(pay, cands, policy)
        if {l.invoice_id for l in _greedy.lines} != {l.invoice_id for l in res.lines}:
            stats["greedy_differs"] += 1
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
        _td = time.perf_counter()
        ded = deduction_intelligence(pay, 100000, 40000, policy) if pay.claimed_deduction_cents else None
        stage_ms["deduction"] += (time.perf_counter() - _td) * 1000
        if ded:
            ded["payer"] = pay.payer_raw; ded["claimed_cents"] = pay.claimed_deduction_cents
            stats["claims"] += 1
            _act = ded.get("autonomous_action") or "JUDGED"
            ded_actions[_act] = ded_actions.get(_act, 0) + 1
        reasoning = _reasoning(pay, cands, matched_by, res, ded, auto, maker_checker, total_open, policy)
        repo.add_match(match_id, run_id, pay.payment_id,
                       "AUTO_POSTED" if auto else "PROPOSED", res.solver, res.residual_cents,
                       res.confidence, {"payment": asdict(pay),
                                        "lines": [asdict(l) for l in res.lines], "deduction_applied": res.deduction_applied,
                                        "matched_by": res.matched_by, "latency_ms": res.latency_ms,
                                        "decision_reason": decision_reason,
                                        "status": status, "auto_posted": auto, "deduction": ded,
                                        "reasoning": reasoning,
                                        "derivation": _deriv})
        if res.lines:
            used = {l.invoice_id for l in res.lines}
            open_invoices = [i for i in open_invoices if i.invoice_id not in used]
        if status != "OPTIMAL_EXACT_MATCH":
            ex = {"payment_id": pay.payment_id, "kind": "UNRESOLVED_RESIDUAL" if res.lines else "NO_MATCH",
                  "severity": "HIGH" if not res.lines else "MEDIUM",
                  "recommended_action": "Review counterfactuals and approve or reassign",
                  "detail": {"residual_cents": res.residual_cents,
                             "payer": pay.payer_raw, "amount_cents": pay.amount_cents}}
            repo.add_exception(run_id, pay.payment_id, ex["kind"], ex["severity"], ex["recommended_action"], ex["detail"])
            exceptions.append(ex)
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
                        "deduction": ded, "reasoning": reasoning, "derivation": derivation})
    total_ms = round((time.perf_counter() - t0) * 1000, 2)
    repo.add_step(run_id, "BatchReconciler", "COMPLETED", total_ms,
                  {"payments": len(payments), "exceptions": len(exceptions)}, None)
    auto_pre = sum(1 for r in results if r["auto_posted"])
    repo.add_step(run_id, "Capture Agent", "COMPLETED", round(stage_ms["capture"], 2),
                  {"payments_received": len(payments), "unique_fingerprints": len(seen_fingerprints),
                   "duplicates_blocked": stats["duplicates"],
                   "reading": "SHA-256 fingerprint per payment (payer, amount, currency); a repeat fingerprint is held before matching, never posted twice."}, None)
    repo.add_step(run_id, "Linking Agent", "COMPLETED", round(stage_ms["linking"], 2),
                  {"rung_histogram": rungs, "candidates_total": stats["candidates_total"],
                   "avg_candidates_per_payment": round(stats["candidates_total"] / max(len(payments), 1), 1),
                   "reading": "Candidate shortlists by resolution rung: references, PO, OCR repair, alias or fuzzy payer, payer plus amount."}, None)
    repo.add_step(run_id, "Matching Agent", "COMPLETED", round(stage_ms["matching"], 2),
                  {"payments_solved": len(payments) - stats["duplicates"], "exact_matches": stats["exact"],
                   "milp_latency_ms_total": round(stats["milp_ms"], 2), "solver": "HiGHS MILP via scipy.optimize.milp, integer cents",
                   "greedy_baseline_differs_on": stats["greedy_differs"],
                   "reading": "Exact sets satisfy the cash conservation equation to the cent; every returned set is re-verified in integer cents before it is believed."}, None)
    repo.add_step(run_id, "Deduction Agent", "COMPLETED", round(stage_ms["deduction"], 2),
                  {"claims_judged": stats["claims"], "actions": ded_actions,
                   "reading": "Each claim classified, z-scored against the payer's history, and priced by expected value: dispute, route to an analyst, or write off inside tolerance."}, None)
    repo.add_step(run_id, "Policy Agent", "COMPLETED", round(stage_ms["policy"], 2),
                  {"auto_posted": auto_pre, "held_for_maker_checker": stats["held"],
                   "proposed_for_review": len(results) - auto_pre, "exceptions_raised": len(exceptions),
                   "automation_threshold": policy.automation_threshold,
                   "maker_checker_threshold_cents": policy.maker_checker_threshold_cents,
                   "reading": "Auto-post needs an exact match at or above the confidence threshold; above the maker-checker amount a second human signs, however sure the solver is."}, None)
    repo.add_step(run_id, "Briefing Agent", "ON_DEMAND", 0.0,
                  {"reading": "The run brief, dispute drafts and chase drafts compose on demand from this run's stored facts; nothing is pre-written or cached."}, None)
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
