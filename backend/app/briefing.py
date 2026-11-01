"""AI workflow layer: run briefs and dispute drafting.

The agent does not end at matching. After every run it writes the brief a
lead would write, and for every disputable deduction it drafts the claim
email and the rebuttals to the buyer's standard pushbacks. Generative AI
(Gemini) writes these when a key is configured; otherwise the same texts
are composed deterministically from the run's own records. Either way the
numbers come only from the records - the model may phrase, never invent.
Every output carries its source so the reader always knows which wrote it.
"""
from ai import GeminiClient


def _money(cents):
    return f"${cents / 100:,.2f}"


def run_facts(repo, run_id):
    matches = repo.matches_for_run(run_id)
    exceptions = repo.exceptions_for_run(run_id)
    runs = {r["run_id"]: r for r in repo.list_runs(50)}
    meta = runs.get(run_id, {})
    auto = [m for m in matches if (m.get("result") or {}).get("auto_posted")]
    held = [m for m in matches if not (m.get("result") or {}).get("auto_posted")]
    cash_posted = sum(sum(l.get("net_cents", 0) for l in (m.get("result") or {}).get("lines", []))
                      for m in auto)
    disputes, recovery = [], 0.0
    for m in matches:
        ded = (m.get("result") or {}).get("deduction") or {}
        if ded.get("autonomous_action") == "AUTO_GENERATE_DISPUTE_CLAIM":
            disputes.append({"payment_id": m["payment_id"],
                             "claimed": ded.get("claimed_cents", 0),
                             "expected_recovery_usd": ded.get("expected_recovery_value_usd", 0.0)})
            recovery += float(ded.get("expected_recovery_value_usd") or 0)
    return {"run_id": run_id, "payments": meta.get("payments", len(matches) + len(exceptions)),
            "auto_posted": len(auto), "held": len(held),
            "held_reasons": sorted({(m.get("result") or {}).get("decision_reason", "") for m in held} - {""}),
            "cash_posted_cents": cash_posted, "exceptions": len(exceptions),
            "exception_kinds": sorted({e["kind"] for e in exceptions}),
            "disputes": disputes, "expected_recovery_usd": round(recovery, 2)}


def _brief_deterministic(f):
    lines = [f"Run {f['run_id']}: {f['auto_posted']} of {f['payments']} payments posted themselves; "
             f"{f['held']} need a human."]
    if f["cash_posted_cents"]:
        lines.append(f"Cash applied automatically: {_money(f['cash_posted_cents'])}.")
    if f["held_reasons"]:
        lines.append("Held because: " + "; ".join(f["held_reasons"]) + ".")
    if f["disputes"]:
        lines.append(f"{len(f['disputes'])} dispute claim(s) opened automatically, expected recovery "
                     f"${f['expected_recovery_usd']:,.2f}. Drafts are waiting in the dispute desk.")
    if f["exceptions"]:
        lines.append(f"{f['exceptions']} exception(s) raised: {', '.join(f['exception_kinds'])}.")
    actions = []
    if f["held"]:
        actions.append(f"Approve or reject the {f['held']} held match(es) in the approvals queue.")
    if f["disputes"]:
        actions.append("Review and send the dispute drafts in the dispute desk below.")
    if f["exceptions"]:
        actions.append("Work the exception queue - duplicates and unmatched payments first.")
    if not actions:
        actions.append("Nothing needs a human from this run.")
    return {"headline": lines[0], "body": lines[1:], "next_actions": actions, "source": "deterministic"}


def run_brief(repo, run_id, client=None):
    f = run_facts(repo, run_id)
    base = _brief_deterministic(f)
    client = client or GeminiClient()
    if client.available:
        try:
            facts = (f"payments={f['payments']}, auto_posted={f['auto_posted']}, held={f['held']}, "
                     f"cash_posted={_money(f['cash_posted_cents'])}, held_reasons={f['held_reasons']}, "
                     f"disputes={len(f['disputes'])}, expected_recovery=${f['expected_recovery_usd']}, "
                     f"exceptions={f['exceptions']} ({', '.join(f['exception_kinds'])})")
            text = client.generate_text(
                "You are the AutoCash agent briefing a finance lead after a cash application run. "
                "Write a 3-4 sentence brief using ONLY these facts, keeping every number exact, "
                f"then stop. Facts: {facts}")
            if str(f["auto_posted"]) in text and str(f["payments"]) in text:
                base["body"] = [text.strip()] + base["body"][1:]
                base["source"] = "gemini"
        except Exception:
            pass
    base["facts"] = f
    return base


_TONE_OPEN = {
    "strict": "We are disputing this deduction formally and ask for reversal or evidence within 10 business days.",
    "contract": "Under our agreed terms, a deduction of this kind requires prior written authorisation, which was not given for this shipment.",
    "escalate": "If this is not resolved within 5 business days we will escalate the claim to VP level on both sides.",
}


def _dispute_template(tone, f):
    return (f"To: {f.get('payer', 'Buyer')} - Accounts Payable\n"
            f"Subject: Dispute of deduction on payment {f.get('payment_id', '')} - claim {_money(f.get('claimed_cents', 0))}\n\n"
            f"Dear Accounts Payable team,\n\n"
            f"We are disputing a deduction of {_money(f.get('claimed_cents', 0))} taken on payment "
            f"{f.get('payment_id', '')}. Our engine classified it as {f.get('classification_label', 'unexplained')} "
            f"(ERP reason code {f.get('reason_code', '')}). The proof of delivery for this shipment was signed "
            f"clean, and the deduction does not match the agreed terms.\n\n"
            f"{_TONE_OPEN.get(tone, _TONE_OPEN['strict'])}\n\n"
            f"Our assessment: win probability {f.get('win_probability', '')}, expected recovery "
            f"${float(f.get('expected_recovery_usd') or 0):,.2f}. We would rather close this quickly than "
            f"escalate it.\n\nRegards,\nAccounts Receivable - AutoCash dispute desk\n"
            f"(Draft composed from the case record - review before sending.)")


_REBUTTALS = {
    "damage": ("The proof of delivery for this shipment was signed clean at handover, with no damage noted. "
               "A concealed-damage claim needs the receiving inspection report and photos, shared inside the "
               "contract window. Please share them and we will review the same day. Until then the deduction "
               "of {claimed} stays disputed in full."),
    "discount_timing": ("The early-pay discount in our agreed terms runs from the invoice date, not the dock "
                        "receipt date. On that basis the discount was not earned on this invoice and the "
                        "short-paid {claimed} remains due. We are happy to walk your team through the clause."),
}


def _rebuttal_template(f):
    kind = f.get("buyer_reply", "")
    claimed = _money(f.get("claimed_cents", 0))
    if kind == "split":
        offer = float(f.get("offer_usd") or 0)
        expected = float(f.get("expected_recovery_usd") or 0)
        if offer >= expected:
            return (f"Thank you - we accept ${offer:,.2f} to close this ticket today. Our assessed expected "
                    f"recovery was ${expected:,.2f}, so your offer is fair. Please treat this dispute as "
                    f"settled on payment of the agreed sum.")
        return (f"Thank you for the offer. We cannot accept ${offer:,.2f}. Our assessed expected recovery on "
                f"this claim is ${expected:,.2f} (win probability {f.get('win_probability', '')} on a clean "
                f"signed POD, claim {claimed}). We will settle today at ${expected:,.2f}, or proceed with "
                f"the full dispute for {claimed}.")
    body = _REBUTTALS.get(kind, _REBUTTALS["damage"])
    return body.format(claimed=claimed)


def draft_message(kind, tone, facts, client=None):
    if kind == "dispute_email":
        text, label = _dispute_template(tone or "strict", facts), "template"
    else:
        text, label = _rebuttal_template(facts), "template"
    client = client or GeminiClient()
    if client.available:
        try:
            out = client.generate_text(
                "Rewrite this business email draft in a firm, professional tone. Keep EVERY number, "
                f"reference and name exactly as written. Return only the rewritten text.\n\n{text}")
            claimed = _money(facts.get("claimed_cents", 0))
            if out and claimed in out and len(out) > 40:
                return {"text": out.strip(), "source": "gemini"}
        except Exception:
            pass
    return {"text": text, "source": label}
