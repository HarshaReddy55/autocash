"""AutoCash API. Run: uvicorn api:app --app-dir backend/app --port 8080
Env: AUTOCASH_DB (default ./autocash.db), GEMINI_API_KEY (optional)."""
import os, json, uuid, hashlib
from dataclasses import asdict
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional

from domain import Invoice, Payment, Policy
from repository import Repository
from ingestion import parse_invoices_csv, parse_payments_csv
from scenarios import SCENARIOS, get_scenario
from methodology import SECTIONS as METHODOLOGY
from batch import run_batch
from anomaly import payment_fingerprint
from solvers import solve_milp, solve_greedy, why_not_invoice
from ai import parse_remittance, GeminiClient
from briefing import run_brief, draft_message
from copilot import answer as copilot_answer
from seed import seed_invoices, seed_payments, GROUND_TRUTH
import ml as mlmod
from forecast import forecast_cash_in, prioritise_collections

DATA_DIR = os.environ.get("AUTOCASH_DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))
from tenants import TenantStore, ROLE_CAPS
store = TenantStore(os.path.abspath(DATA_DIR))
BOOTSTRAP_KEY = os.environ.get("AUTOCASH_BOOTSTRAP_KEY", "")
_repos = {}
_models = {}

def _now_iso():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()

def repo_for(tenant_id):
    if tenant_id not in _repos:
        _repos[tenant_id] = Repository(store.db_path(tenant_id))
    return _repos[tenant_id]

from fastapi import Header, HTTPException, Depends
from fastapi.responses import StreamingResponse
import queue as _queue, threading as _threading, time as _time

def auth_context(x_api_key: str = Header(default="")):
    """Returns {tenant_id, role}. Dev mode: when no bootstrap key and no keys
    exist yet for the store, requests map to the built-in demo tenant so the
    product runs locally without setup. In production set AUTOCASH_BOOTSTRAP_KEY
    and issue tenant keys; dev mode then disables automatically once any key exists."""
    any_keys = store.conn.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0] > 0
    if not any_keys and not BOOTSTRAP_KEY:
        if not store.tenant_exists("demo"):
            store.conn.execute("INSERT OR IGNORE INTO tenants VALUES ('demo','Demo workspace',0)"); store.conn.commit()
        return {"tenant_id": "demo", "role": "admin", "mode": "dev-open"}
    ctx = store.resolve(x_api_key)
    if ctx is None:
        raise HTTPException(401, "invalid or missing API key")
    ctx["mode"] = "key"
    return ctx

def need(ctx, cap):
    if cap not in ROLE_CAPS[ctx["role"]]:
        raise HTTPException(403, f"role {ctx['role']} lacks capability {cap}")
    return ctx

def models():
    if "m" not in _models:
        _models["m"] = mlmod.train_all()
    return _models["m"]

app = FastAPI(title="AutoCash - Autonomous Cash Application Agent")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class PaymentIn(BaseModel):
    payment_id: str; payer_raw: str; amount_cents: int; currency: str = "USD"
    claimed_deduction_cents: int = 0; deduction_reason_raw: str = ""
    pod_verified_clean: bool = False; remittance_text: str = ""; references: List[str] = []

class BatchIn(BaseModel):
    idempotency_key: str
    payments: List[PaymentIn]
    policy: Optional[dict] = None

class ParseIn(BaseModel):
    text: str

class CopilotIn(BaseModel):
    question: str

class WhyNotIn(BaseModel):
    payment: PaymentIn
    invoice_id: str

def _pay(p: PaymentIn) -> Payment:
    return Payment(**p.model_dump())

@app.get("/health")
def health():
    return {"status": "ok", "gemini_configured": GeminiClient().available,
            "model_metrics": models()["metrics"], "data_dir": os.path.basename(DATA_DIR),
            "auth": "api-key" if (BOOTSTRAP_KEY or store.conn.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0]) else "dev-open"}

@app.post("/api/v1/seed")
def seed(ctx=Depends(auth_context)):
    need(ctx, "run"); repo = repo_for(ctx["tenant_id"])
    invs = seed_invoices()
    for inv in invs: repo.add_invoice(inv)
    pays = seed_payments()
    for p in pays: repo.add_payment(p, payment_fingerprint(p))
    if not repo.get_meta("active_case"):
        repo.set_meta("active_case", {"id": "seed", "name": "Demo seed workspace", "source": "demo-seed",
                                      "loaded_at": _now_iso(),
                                      "expect": {pid: {"invoices": sorted(s)} for pid, s in GROUND_TRUTH.items()},
                                      "expect_exceptions": {}})
    return {"invoices": len(invs), "payments": [asdict(p) for p in pays],
            "note": "Synthetic labelled workspace for evaluation. Payments are returned for review, then submitted to /api/v1/batches."}

def _workspace_state(repo):
    """The one shared truth every view reads: the active case, what is staged,
    what the latest run did, and what is waiting for a human."""
    pending = repo.pending_payments()
    runs = repo.list_runs(1)
    return {"case": repo.get_meta("active_case"),
            "open_invoices": len(repo.open_invoices()),
            "staged_payments": len(repo.all_payments()),
            "pending_payments": [asdict(p) for p in pending],
            "latest_run": runs[0] if runs else None,
            "approvals_pending": len(repo.list_proposed())}

@app.get("/api/v1/workspace")
def workspace(ctx=Depends(auth_context)):
    need(ctx, "read"); return _workspace_state(repo_for(ctx["tenant_id"]))

def _policy_for(repo, tenant_id, body_policy):
    """Effective run policy: an explicit request body wins; otherwise the
    tenant's stored policy, with the active use-case pack's grading override
    (if any) applied on top."""
    if body_policy: return Policy(**body_policy)
    stored = store.get_policy(tenant_id)
    base = dict(stored) if stored else {}
    case = repo.get_meta("active_case") or {}
    for k, v in (case.get("policy") or {}).items(): base[k] = v
    return Policy(**base) if base else Policy()

def _load_case(repo, cid, actor):
    """Replace the workspace with one case, so every view works on the same
    data: dashboard, ledger, run, approvals, forecast and copilot all read
    this one workspace."""
    if cid == "seed":
        invs, pays = seed_invoices(), seed_payments()
        name, source = "Demo seed workspace", "demo-seed"
        expect = {pid: {"invoices": sorted(s)} for pid, s in GROUND_TRUTH.items()}
        expect_exc = {}
    else:
        sc = get_scenario(cid)
        if not sc: raise HTTPException(404, f"unknown case {cid}")
        invs, pays = sc["build"]()
        name, source = sc["title"], "use-case"
        raw = dict(sc.get("expect") or {})
        expect_exc = raw.pop("exceptions", {}) if isinstance(raw.get("exceptions"), dict) else {}
        expect = {}
        for pid, e in raw.items():
            if isinstance(e, dict):
                expect[pid] = {k: (sorted(v) if isinstance(v, (set, list)) and k == "invoices" else v)
                               for k, v in e.items()}
    repo.clear_workspace()
    for inv in invs: repo.add_invoice(inv)
    for p in pays: repo.add_payment(p, payment_fingerprint(p))
    meta = {"id": cid, "name": name, "source": source,
            "loaded_at": _now_iso(), "expect": expect,
            "expect_exceptions": expect_exc}
    if source == "use-case":
        # Same grading policy as the scenario endpoint: the maker-checker
        # threshold is raised while a pack is the active case, so the run's
        # verdict isolates matching correctness on enterprise amounts.
        # Approval gating itself lives in Policy Studio and its own flow.
        meta["policy"] = {"maker_checker_threshold_cents": 10**12}
        meta["policy_note"] = "Maker-checker threshold is raised for this use case, so its verdict isolates matching correctness (the same grading policy the pack states). Policy Studio still governs uploaded and demo data."
    repo.set_meta("active_case", meta)
    repo.audit(actor, "case_loaded", "workspace", cid,
               {"invoices": len(invs), "payments": len(pays)}, _now_iso())
    return pays

@app.post("/api/v1/cases/{cid}/load")
def load_case(cid: str, ctx=Depends(auth_context)):
    need(ctx, "run"); repo = repo_for(ctx["tenant_id"])
    pays = _load_case(repo, cid, f"api:{ctx['role']}")
    return {"workspace": _workspace_state(repo), "payments": [asdict(p) for p in pays]}

@app.post("/api/v1/workspace/reset")
def workspace_reset(ctx=Depends(auth_context)):
    need(ctx, "run"); repo = repo_for(ctx["tenant_id"])
    repo.clear_workspace()
    repo.audit(f"api:{ctx['role']}", "workspace_reset", "workspace", "", {}, _now_iso())
    return _workspace_state(repo)

class StagePaymentIn(BaseModel):
    payment_id: str = ""; payer: str = ""; amount_cents: int = 0
    references: List[str] = []; claimed_deduction_cents: int = 0
    deduction_reason: str = ""; pod_verified_clean: bool = False
    remittance_text: str = ""

@app.post("/api/v1/workspace/stage-payment")
def stage_payment(body: StagePaymentIn, ctx=Depends(auth_context)):
    """Stage one parsed wire into the shared workspace (parsed in Upload,
    reconciled in Run - the same flow as files and cases)."""
    need(ctx, "run"); repo = repo_for(ctx["tenant_id"])
    if int(body.amount_cents or 0) <= 0:
        raise HTTPException(422, "amount_cents must be positive - parse the remittance first")
    pid = (body.payment_id or "").strip() or ("WIRE-" + uuid.uuid4().hex[:8].upper())
    repo.add_payment(Payment(payment_id=pid, payer_raw=body.payer or "Unknown payer",
                             amount_cents=int(body.amount_cents),
                             claimed_deduction_cents=int(body.claimed_deduction_cents or 0),
                             deduction_reason_raw=body.deduction_reason or "",
                             pod_verified_clean=bool(body.pod_verified_clean),
                             remittance_text=body.remittance_text or "",
                             references=list(body.references or [])))
    if not repo.get_meta("active_case"):
        repo.set_meta("active_case", {"id": "ingested", "name": "Ingested remittance",
                                      "source": "Remittance paste in Upload Center",
                                      "loaded_at": _now_iso()})
    repo.audit(f"api:{ctx['role']}", "payment_staged", "payment", pid,
               {"amount_cents": int(body.amount_cents)}, _now_iso())
    return {"staged": pid, "workspace": _workspace_state(repo)}

@app.get("/api/v1/invoices")
def invoices(ctx=Depends(auth_context)):
    need(ctx, "read"); return [asdict(i) for i in repo_for(ctx["tenant_id"]).open_invoices()]

@app.post("/api/v1/invoices/import")
def import_invoices(payload: dict, ctx=Depends(auth_context)):
    need(ctx, "run"); repo = repo_for(ctx["tenant_id"])
    was_empty = len(repo.open_invoices()) == 0 and not repo.get_meta("active_case")
    out = parse_invoices_csv(payload.get("csv_text", ""))
    for inv in out["invoices"]: repo.add_invoice(inv)
    if was_empty and out["invoices"]:
        repo.set_meta("active_case", {"id": "upload", "name": "Uploaded ledger", "source": "upload",
                                      "loaded_at": _now_iso(), "expect": {}, "expect_exceptions": {}})
    return {"imported": len(out["invoices"]), "mapping": out["mapping"], "errors": out["errors"], "fingerprint": out["fingerprint"]}

@app.post("/api/v1/batches")
def batches(body: BatchIn, ctx=Depends(auth_context)):
    need(ctx, "run"); repo = repo_for(ctx["tenant_id"])
    pol = _policy_for(repo, ctx["tenant_id"], body.policy)
    pays = [_pay(p) for p in body.payments]
    for p in pays: repo.add_payment(p, payment_fingerprint(p))
    return run_batch(repo, pays, pol, body.idempotency_key, actor=f"api:{ctx['role']}")

@app.post("/api/v1/payments/import")
def import_payments(payload: dict, ctx=Depends(auth_context)):
    """Upload a payments CSV: parse it, then reconcile it as a batch."""
    need(ctx, "run"); repo = repo_for(ctx["tenant_id"])
    out = parse_payments_csv(payload.get("csv_text", ""))
    for p in out["payments"]: repo.add_payment(p, payment_fingerprint(p))
    if out["payments"] and not repo.get_meta("active_case"):
        repo.set_meta("active_case", {"id": "upload", "name": "Uploaded files", "source": "upload",
                                      "loaded_at": _now_iso(), "expect": {}, "expect_exceptions": {}})
    pol = _policy_for(repo, ctx["tenant_id"], None)
    import uuid as _uuid
    run = run_batch(repo, out["payments"], pol, payload.get("idempotency_key") or ("csv-" + _uuid.uuid4().hex[:10]),
                    actor=f"api:{ctx['role']}") if out["payments"] else None
    return {"imported": len(out["payments"]), "mapping": out["mapping"], "errors": out["errors"],
            "fingerprint": out["fingerprint"], "run": run}

@app.get("/api/v1/runs")
def list_runs(ctx=Depends(auth_context)):
    need(ctx, "read"); return repo_for(ctx["tenant_id"]).list_runs()

@app.get("/api/v1/methodology")
def methodology():
    """How every number is computed - served with the code it describes."""
    return {"sections": METHODOLOGY}

@app.get("/api/v1/scenarios")
def scenarios():
    out = []
    for s in SCENARIOS:
        invs, pays = s["build"]()
        out.append({"id": s["id"], "title": s["title"], "story": s["story"], "shows": s["shows"],
                    "invoices": len(invs), "payments": len(pays),
                    "customers": len({i.customer for i in invs}),
                    "open_cents": sum(i.gross_cents for i in invs),
                    "batch_cents": sum(p.amount_cents for p in pays)})
    return out

@app.post("/api/v1/scenarios/custom/run")
def run_custom_case(payload: dict, ctx=Depends(auth_context)):
    """Build-your-own case: caller-supplied invoices and payments, run in a
    clean room against the production engine. Every result carries the full
    derivation, so a reviewer can test the engine on their own numbers."""
    need(ctx, "run")
    from domain import Invoice as _Inv, Payment as _Pay
    invs = [_Inv(invoice_id=str(i["invoice_id"]), customer=str(i.get("customer", "UNKNOWN")),
                 subsidiary=str(i.get("customer", "UNKNOWN")), gross_cents=int(i["gross_cents"]),
                 po_number=i.get("po_number") or None, discount_rate=float(i.get("discount_rate", 0) or 0),
                 age_days=int(i.get("age_days", 0) or 0)) for i in payload.get("invoices", [])]
    pays = [_Pay(payment_id=str(p["payment_id"]), payer_raw=str(p.get("payer_raw", "UNKNOWN")),
                 amount_cents=int(p["amount_cents"]), claimed_deduction_cents=int(p.get("claimed_deduction_cents", 0) or 0),
                 deduction_reason_raw=str(p.get("deduction_reason_raw", "") or ""),
                 pod_verified_clean=bool(p.get("pod_verified_clean", False)),
                 remittance_text=str(p.get("remittance_text", "") or ""),
                 references=list(p.get("references", []) or [])) for p in payload.get("payments", [])]
    if not invs or not pays: raise HTTPException(400, "a case needs at least one invoice and one payment")
    mem = Repository(":memory:")
    for inv in invs: mem.add_invoice(inv)
    run = run_batch(mem, pays, Policy(), "custom-" + uuid.uuid4().hex[:8], actor="custom-case")
    return {"run": run}

@app.post("/api/v1/workspace/load-custom")
def load_custom_case(payload: dict, ctx=Depends(auth_context)):
    """Builder cases join the same shared workspace as every other case:
    staged here, they run from Run Reconciliation like anything else."""
    need(ctx, "run"); repo = repo_for(ctx["tenant_id"])
    from domain import Invoice as _Inv, Payment as _Pay
    invs = [_Inv(invoice_id=str(i["invoice_id"]), customer=str(i.get("customer", "UNKNOWN")),
                 subsidiary=str(i.get("customer", "UNKNOWN")), gross_cents=int(i["gross_cents"]),
                 po_number=i.get("po_number") or None, discount_rate=float(i.get("discount_rate", 0) or 0),
                 age_days=int(i.get("age_days", 0) or 0)) for i in payload.get("invoices", [])]
    pays = [_Pay(payment_id=str(p["payment_id"]), payer_raw=str(p.get("payer_raw", "UNKNOWN")),
                 amount_cents=int(p["amount_cents"]), claimed_deduction_cents=int(p.get("claimed_deduction_cents", 0) or 0),
                 deduction_reason_raw=str(p.get("deduction_reason_raw", "") or ""),
                 pod_verified_clean=bool(p.get("pod_verified_clean", False)),
                 remittance_text=str(p.get("remittance_text", "") or ""),
                 references=list(p.get("references", []) or [])) for p in payload.get("payments", [])]
    if not invs or not pays: raise HTTPException(400, "a case needs at least one invoice and one payment")
    repo.clear_workspace()
    for inv in invs: repo.add_invoice(inv)
    for p in pays: repo.add_payment(p, payment_fingerprint(p))
    repo.set_meta("active_case", {"id": "custom", "name": "Custom case (builder)", "source": "custom",
                                  "loaded_at": _now_iso(), "expect": {}, "expect_exceptions": {}})
    repo.audit(f"api:{ctx['role']}", "case_loaded", "workspace", "custom",
               {"invoices": len(invs), "payments": len(pays)}, _now_iso())
    return {"workspace": _workspace_state(repo), "payments": [asdict(p) for p in pays]}

@app.post("/api/v1/scenarios/{sid}/run")
def run_scenario(sid: str, ctx=Depends(auth_context)):
    """Clean-room scenario run: a fresh in-memory ledger, so use cases never
    pollute the workspace. The outcome is verified against the pack's stated
    expectations and every check is reported, pass or fail."""
    need(ctx, "run")
    sc = get_scenario(sid)
    if not sc: raise HTTPException(404, "unknown scenario")
    invs, pays = sc["build"]()
    mem = Repository(":memory:")
    for inv in invs: mem.add_invoice(inv)
    # Grading policy: identical to production except the maker-checker
    # threshold is raised, so a pack's verdict isolates matching correctness.
    # Approval gating itself is covered by the approvals queue and its tests.
    run = run_batch(mem, pays, Policy(maker_checker_threshold_cents=10**12),
                    f"scenario-{sid}", actor="scenario")
    by_pid = {r["payment_id"]: r for r in run["results"]}
    ex_by_pid = {e["payment_id"]: e["kind"] for e in run["exceptions"]}
    checks = []
    for pid, exp in sc["expect"].items():
        if pid == "exceptions":
            for epid, kind in exp.items():
                actual = ex_by_pid.get(epid)
                checks.append({"label": f"{epid} flagged {kind}", "expected": kind, "actual": actual, "pass": actual == kind})
            continue
        r = by_pid.get(pid, {})
        if "status" in exp:
            checks.append({"label": f"{pid} status", "expected": exp["status"], "actual": r.get("status"), "pass": r.get("status") == exp["status"]})
        if "auto_posted" in exp:
            checks.append({"label": f"{pid} auto-posted", "expected": exp["auto_posted"], "actual": r.get("auto_posted"), "pass": r.get("auto_posted") == exp["auto_posted"]})
        if "invoices" in exp:
            got = {l["invoice_id"] for l in r.get("lines", [])}
            checks.append({"label": f"{pid} matched invoices", "expected": sorted(exp["invoices"]), "actual": sorted(got), "pass": got == exp["invoices"]})
        if "residual_cents" in exp:
            checks.append({"label": f"{pid} residual", "expected": exp["residual_cents"], "actual": r.get("residual_cents"), "pass": r.get("residual_cents") == exp["residual_cents"]})
        if "deduction_action" in exp:
            ded = r.get("deduction") or {}
            checks.append({"label": f"{pid} deduction decision", "expected": exp["deduction_action"], "actual": ded.get("autonomous_action"), "pass": ded.get("autonomous_action") == exp["deduction_action"]})
            checks.append({"label": f"{pid} ERP reason code", "expected": exp["erp_reason_code"], "actual": ded.get("assigned_erp_reason_code"), "pass": ded.get("assigned_erp_reason_code") == exp["erp_reason_code"]})
        if "spike" in exp:
            ded = r.get("deduction") or {}
            checks.append({"label": f"{pid} anomaly spike flagged", "expected": exp["spike"], "actual": ded.get("is_anomalous_spike"), "pass": ded.get("is_anomalous_spike") == exp["spike"]})
    return {"policy_note": "Graded under the production policy with the maker-checker threshold raised, so the verdict isolates matching correctness; approval gating is exercised separately in the approvals queue.",
            "scenario": {"id": sc["id"], "title": sc["title"], "story": sc["story"], "shows": sc["shows"]},
            "run": run, "checks": checks, "all_pass": all(c["pass"] for c in checks)}


class StreamIn(BaseModel):
    seed: bool = False
    payments: list[PaymentIn] = []
    policy: dict | None = None
    use_workspace: bool = False

@app.post("/api/v1/runs/stream")
def run_stream(body: StreamIn, ctx=Depends(auth_context)):
    """Live run: the batch engine streams every mechanism step as it happens
    (resolve -> solve -> deduction -> decision) over server-sent events."""
    need(ctx, "run"); repo = repo_for(ctx["tenant_id"])
    if body.seed:
        payments = _load_case(repo, "seed", f"api:{ctx['role']}")
    elif body.payments:
        payments = [_pay(p) for p in body.payments]
        for p in payments: repo.add_payment(p, payment_fingerprint(p))
    elif body.use_workspace:
        payments = repo.pending_payments() or repo.all_payments()
    else:
        payments = []
    pol = _policy_for(repo, ctx["tenant_id"], body.policy)
    q = _queue.Queue()
    def _run():
        try:
            run_batch(repo, payments, pol, "live-" + uuid.uuid4().hex[:10],
                      actor=f"api:{ctx['role']}", on_event=q.put)
        except Exception as e:
            q.put({"type": "error", "message": str(e)})
        finally:
            q.put(None)
    _threading.Thread(target=_run, daemon=True).start()
    def gen():
        while True:
            item = q.get()
            if item is None: break
            yield f"data: {json.dumps(item)}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.get("/api/v1/approvals")
def approvals(ctx=Depends(auth_context)):
    need(ctx, "read"); return repo_for(ctx["tenant_id"]).list_proposed()

class DecisionIn(BaseModel):
    decision: str

@app.post("/api/v1/matches/{match_id}/decision")
def match_decision(match_id: str, body: DecisionIn, ctx=Depends(auth_context)):
    need(ctx, "approve"); repo = repo_for(ctx["tenant_id"])
    m = repo.get_match(match_id)
    if not m: raise HTTPException(404, "match not found")
    if m["status"] != "PROPOSED": raise HTTPException(409, f"match is {m['status']}, not PROPOSED")
    if body.decision not in ("approve", "reject"): raise HTTPException(422, "decision must be approve or reject")
    res = m["result"]
    res["approval"] = {"decision": body.decision, "by_role": ctx["role"], "at": _now_iso()}
    new_status = "APPROVED_POSTED" if body.decision == "approve" else "REJECTED"
    repo.update_match(match_id, new_status, res)
    repo.audit(f"api:{ctx['role']}", f"match_{body.decision}d", "match", match_id,
               {"payment_id": m["payment_id"], "run_id": m["run_id"]}, _now_iso())
    return {"match_id": match_id, "status": new_status}

@app.get("/api/v1/audit")
def audit_trail(ctx=Depends(auth_context)):
    need(ctx, "read"); return repo_for(ctx["tenant_id"]).audit_list()

@app.get("/api/v1/runs/{run_id}/matches")
def run_matches(run_id: str, ctx=Depends(auth_context)):
    need(ctx, "read"); return repo_for(ctx["tenant_id"]).matches_for_run(run_id)

@app.get("/api/v1/runs/{run_id}/exceptions")
def run_exceptions(run_id: str, ctx=Depends(auth_context)):
    need(ctx, "read"); return repo_for(ctx["tenant_id"]).exceptions_for_run(run_id)

@app.post("/api/v1/parse")
def parse(body: ParseIn, ctx=Depends(auth_context)):
    need(ctx, "parse"); invs = repo_for(ctx["tenant_id"]).open_invoices()
    t0 = _time.perf_counter()
    out = parse_remittance(body.text, {i.invoice_id for i in invs}, {i.po_number for i in invs if i.po_number})
    extract_ms = round((_time.perf_counter() - t0) * 1000, 1)
    f = out["fields"]; v = out["verification"]
    checked = len(f.get("invoice_refs", [])) + len(f.get("po_refs", []))
    out["ai_mode"] = "gemini" if out["source"] == "gemini" else "deterministic"
    out["pipeline"] = [
        {"stage": "1. Extract", "engine": out["source"], "ms": extract_ms,
         "detail": "AI reads the free text and proposes structured fields" if out["source"] == "gemini"
                   else "Deterministic extractor proposes structured fields (Gemini activates when a server key is configured)"},
        {"stage": "2. Schema check", "engine": "validator", "ms": 0,
         "detail": "Required fields present: payer, amount, invoice refs, PO refs, deduction"},
        {"stage": "3. Verify references", "engine": "ledger check", "ms": 0,
         "detail": f"{checked} reference(s) checked against the open ledger; {len(v['issues'])} flagged",
         "issues": v["issues"]},
        {"stage": "4. Trust decision", "engine": "policy", "ms": 0,
         "detail": "Verified - safe to reconcile" if v["verified"] else "Not fully verified - flagged references must be resolved by a human first"}]
    return out

@app.get("/api/v1/runs/{run_id}/brief")
def run_brief_ep(run_id: str, ctx=Depends(auth_context)):
    """The agent's own brief of a finished run - what it posted, what it
    held and why, and what a human should do next."""
    need(ctx, "read"); repo = repo_for(ctx["tenant_id"])
    if run_id not in {r["run_id"] for r in repo.list_runs(50)}:
        raise HTTPException(404, "unknown run")
    return run_brief(repo, run_id)

class DraftIn(BaseModel):
    kind: str = "dispute_email"; tone: str = "strict"; facts: dict = {}

@app.post("/api/v1/ai/draft")
def ai_draft(body: DraftIn, ctx=Depends(auth_context)):
    """Draft a dispute email or a negotiation rebuttal from case facts.
    Gemini rewrites when a key is configured; the grounded template is
    the fallback and the source is always returned."""
    need(ctx, "run")
    if body.kind not in ("dispute_email", "rebuttal"):
        raise HTTPException(422, "kind must be dispute_email or rebuttal")
    return draft_message(body.kind, body.tone, body.facts or {})

@app.post("/api/v1/copilot")
def copilot(body: CopilotIn, ctx=Depends(auth_context)):
    need(ctx, "read"); return copilot_answer(repo_for(ctx["tenant_id"]), body.question, models()["delay_model"])

@app.get("/api/v1/forecast")
def forecast(ctx=Depends(auth_context)):
    need(ctx, "read"); invs = repo_for(ctx["tenant_id"]).open_invoices()
    return forecast_cash_in(invs, models()["delay_model"]) if invs else {"weeks": [], "invoices": []}

@app.get("/api/v1/collections")
def collections(ctx=Depends(auth_context)):
    need(ctx, "read"); return prioritise_collections(repo_for(ctx["tenant_id"]).open_invoices(), models()["delay_model"])

@app.post("/api/v1/why-not")
def why_not(body: WhyNotIn, ctx=Depends(auth_context)):
    need(ctx, "read"); invs = repo_for(ctx["tenant_id"]).open_invoices()
    return why_not_invoice(_pay(body.payment), invs, body.invoice_id, Policy())

@app.get("/api/v1/evaluations")
def evaluations():
    """Live evaluation on the labelled seed scenarios (fresh temp DB per call
    is unnecessary: scenarios run in-memory against the seed ledger)."""
    invs = seed_invoices(); pays = {p.payment_id: p for p in seed_payments()}
    rows, correct, exact = [], 0, 0
    greedy_correct = 0
    for pid, truth in GROUND_TRUTH.items():
        pay = pays[pid]
        from batch import resolve_candidates
        cands, _src = resolve_candidates(pay, invs, {})
        m = solve_milp(pay, cands, Policy())
        g = solve_greedy(pay, cands, Policy())
        got = {l.invoice_id for l in m.lines}
        ok = got == truth
        correct += ok; exact += (m.residual_cents == 0)
        greedy_correct += ({l.invoice_id for l in g.lines} == truth)
        rows.append({"payment_id": pid, "expected": sorted(truth), "milp_got": sorted(got),
                     "milp_residual_cents": m.residual_cents, "milp_correct": ok,
                     "greedy_correct": {l.invoice_id for l in g.lines} == truth})
    n = len(GROUND_TRUTH)
    return {"cases": rows, "milp_accuracy": round(correct / n, 4), "greedy_accuracy": round(greedy_correct / n, 4),
            "milp_exact_rate": round(exact / n, 4),
            "basis": "Labelled synthetic seed scenarios (split, PO-won, discount+deduction, exact). Computed live per call."}



# ---- Admin / tenancy ----
class TenantIn(BaseModel):
    name: str
class KeyIn(BaseModel):
    role: str; label: str = ""
class PolicyIn(BaseModel):
    policy: dict

def _bootstrap(x_api_key: str = Header(default="")):
    if not BOOTSTRAP_KEY or x_api_key != BOOTSTRAP_KEY:
        raise HTTPException(401, "bootstrap key required")
    return True

@app.post("/admin/tenants")
def admin_create_tenant(body: TenantIn, ok=Depends(_bootstrap)):
    tid = store.create_tenant(body.name)
    return {"tenant_id": tid, "name": body.name}

@app.post("/admin/tenants/{tenant_id}/keys")
def admin_issue_key(tenant_id: str, body: KeyIn, ok=Depends(_bootstrap)):
    if not store.tenant_exists(tenant_id): raise HTTPException(404, "tenant not found")
    raw = store.issue_key(tenant_id, body.role, body.label)
    return {"api_key": raw, "tenant_id": tenant_id, "role": body.role,
            "note": "Shown once. Store it in your secrets manager; only its hash is kept here."}

@app.get("/api/v1/policy")
def get_policy(ctx=Depends(auth_context)):
    need(ctx, "read")
    return {"policy": store.get_policy(ctx["tenant_id"]) or asdict(Policy()), "source": "tenant" if store.get_policy(ctx["tenant_id"]) else "default"}

@app.put("/api/v1/policy")
def put_policy(body: PolicyIn, ctx=Depends(auth_context)):
    need(ctx, "admin")
    Policy(**body.policy)  # validate against domain policy fields
    store.set_policy(ctx["tenant_id"], body.policy)
    return {"saved": True}


# ---- Observability: request ids, structured logs, metrics, readiness, rate limits ----
import time as _time, uuid as _uuid, collections as _collections
from fastapi import Request
from fastapi.responses import JSONResponse, PlainTextResponse

_metrics = {"counts": _collections.Counter(), "latency_ms": _collections.Counter()}
_rate_windows = _collections.defaultdict(list)

def _rate_limit_per_min():
    try: return int(os.environ.get("AUTOCASH_RATE_LIMIT_PER_MIN", "300"))
    except Exception: return 300

@app.middleware("http")
async def ops_middleware(request: Request, call_next):
    rid = request.headers.get("x-request-id") or str(_uuid.uuid4())
    key_id = request.headers.get("x-api-key", "anon")
    bucket = hashlib.sha256(key_id.encode()).hexdigest()[:12] if key_id != "anon" else "anon"
    now = _time.time()
    win = [t for t in _rate_windows[bucket] if now - t < 60]
    limit = _rate_limit_per_min()
    if len(win) >= limit and request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "rate limit exceeded", "request_id": rid}, status_code=429,
                            headers={"Retry-After": "60", "X-Request-Id": rid})
    win.append(now); _rate_windows[bucket] = win
    start = _time.time()
    response = await call_next(request)
    dur_ms = round((_time.time() - start) * 1000, 2)
    route = request.url.path
    _metrics["counts"][(route, str(response.status_code))] += 1
    _metrics["latency_ms"][route] += dur_ms
    response.headers["X-Request-Id"] = rid
    print(json.dumps({"ts": round(now, 3), "request_id": rid, "method": request.method,
                      "path": route, "status": response.status_code, "duration_ms": dur_ms,
                      "key_bucket": bucket}), flush=True)
    return response

@app.get("/metrics")
def metrics():
    lines = ["# HELP autocash_requests_total Requests by path and status", "# TYPE autocash_requests_total counter"]
    for (path, status), n in sorted(_metrics["counts"].items()):
        lines.append(f'autocash_requests_total{{path="{path}",status="{status}"}} {n}')
    lines += ["# HELP autocash_request_latency_ms_total Cumulative latency per path", "# TYPE autocash_request_latency_ms_total counter"]
    for path, ms in sorted(_metrics["latency_ms"].items()):
        lines.append(f'autocash_request_latency_ms_total{{path="{path}"}} {ms}')
    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain")

@app.get("/ready")
def ready():
    checks = {}
    try:
        store.conn.execute("SELECT 1").fetchone(); checks["control_db"] = "ok"
    except Exception as e: checks["control_db"] = f"error: {type(e).__name__}"
    checks["data_dir_writable"] = "ok" if os.access(DATA_DIR, os.W_OK) else "error"
    try:
        models(); checks["models"] = "ok"
    except Exception as e: checks["models"] = f"error: {type(e).__name__}"
    ok = all(v == "ok" for v in checks.values())
    return JSONResponse({"ready": ok, "checks": checks}, status_code=200 if ok else 503)

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=os.path.abspath(FRONTEND_DIR), html=True), name="frontend")
