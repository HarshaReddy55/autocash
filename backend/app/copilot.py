"""Grounded copilot: answers only from product records, with citations.
Actions are typed tools requiring confirmation; nothing executes silently."""
import re

def _latest_run_id(repo):
    r = repo.conn.execute("SELECT run_id FROM runs ORDER BY created_at DESC LIMIT 1").fetchone()
    return r[0] if r else None

def answer(repo, question, delay_model=None):
    q = question.lower()
    run_id = _latest_run_id(repo)
    if not run_id:
        return {"answer": "No reconciliation run exists yet. Run a batch first, then ask me about it.",
                "citations": [], "action": None}
    matches = repo.matches_for_run(run_id)
    exceptions = repo.exceptions_for_run(run_id)
    m = re.search(r"why (?:was|is) (p\d+|payment \d+|\S+) not matched", q)
    if "not matched" in q or "unmatched" in q:
        pid = None
        pm = re.search(r"\b(P\d+)\b", question)
        if pm: pid = pm.group(1)
        ex = [e for e in exceptions if (pid is None or e["payment_id"] == pid) and e["kind"] in ("NO_MATCH", "UNRESOLVED_RESIDUAL")]
        if ex:
            e = ex[0]
            return {"answer": f"{e['payment_id']} is in exceptions as {e['kind']} with residual "
                              f"${e['detail'].get('residual_cents', 0)/100:.2f}. Recommended action: {e['recommended_action']}.",
                    "citations": [f"exception:{e['payment_id']}:{e['kind']}", f"run:{run_id}"], "action": None}
        return {"answer": "No unmatched payment matches that description in the latest run.",
                "citations": [f"run:{run_id}"], "action": None}
    if "exception" in q:
        thr = re.search(r"above \$?([0-9,]+)", q)
        items = exceptions
        if thr:
            t = int(thr.group(1).replace(",", "")) * 100
            items = [e for e in items if abs(e["detail"].get("residual_cents", 0)) >= t]
        return {"answer": f"{len(items)} open exception(s) in the latest run: " +
                          "; ".join(f"{e['payment_id']} {e['kind']} ({e['severity']})" for e in items[:8]) or "none",
                "citations": [f"run:{run_id}"] + [f"exception:{e['payment_id']}" for e in items[:8]], "action": None}
    if "touchless" in q or "automation" in q:
        auto = sum(1 for x in matches if x["status"] == "AUTO_POSTED")
        return {"answer": f"Touchless rate in the latest run: {auto}/{len(matches)} matches auto-posted "
                          f"({(auto/max(len(matches),1))*100:.1f}%). This is computed from stored run outcomes on the data in this workspace.",
                "citations": [f"run:{run_id}"], "action": None}
    if "run" in q and ("solver" in q or "batch" in q or "reconciliation" in q):
        return {"answer": "I can start a batch reconciliation run. This is an action, so it needs your confirmation.",
                "citations": [], "action": {"tool": "run_batch", "requires_confirmation": True, "args": {}}}
    return {"answer": "The data in this workspace does not contain an answer to that. Ask me about a payment, exceptions, or the touchless rate for the latest run.",
            "citations": [f"run:{run_id}"], "action": None}
