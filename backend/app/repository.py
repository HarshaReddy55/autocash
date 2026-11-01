"""SQLite repository layer (WAL). Services never touch SQL directly.
Schema is Postgres-compatible in spirit: plain types, integer cents."""
import sqlite3, json, os, threading

SCHEMA = """
CREATE TABLE IF NOT EXISTS invoices(
  invoice_id TEXT PRIMARY KEY, customer TEXT, subsidiary TEXT, gross_cents INTEGER,
  currency TEXT, po_number TEXT, discount_rate REAL, age_days INTEGER, due_in_days INTEGER,
  predicted_delay_days REAL, status TEXT DEFAULT 'OPEN');
CREATE TABLE IF NOT EXISTS payments(
  payment_id TEXT PRIMARY KEY, payer_raw TEXT, payer_customer TEXT, amount_cents INTEGER,
  currency TEXT, claimed_deduction_cents INTEGER, deduction_reason_raw TEXT,
  pod_verified_clean INTEGER, remittance_text TEXT, fingerprint TEXT);
CREATE TABLE IF NOT EXISTS runs(
  run_id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE, kind TEXT, status TEXT,
  policy_json TEXT, created_at TEXT, finished_at TEXT);
CREATE TABLE IF NOT EXISTS run_steps(
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, agent_name TEXT, status TEXT,
  latency_ms REAL, evidence_json TEXT, confidence REAL);
CREATE TABLE IF NOT EXISTS matches(
  match_id TEXT PRIMARY KEY, run_id TEXT, payment_id TEXT, status TEXT,
  solver TEXT, residual_cents INTEGER, confidence REAL, result_json TEXT);
CREATE TABLE IF NOT EXISTS exceptions(
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, payment_id TEXT, kind TEXT,
  severity TEXT, recommended_action TEXT, detail_json TEXT, status TEXT DEFAULT 'OPEN');
CREATE TABLE IF NOT EXISTS audit_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, actor TEXT, action TEXT, entity TEXT,
  entity_id TEXT, payload_json TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS aliases(
  raw_name TEXT PRIMARY KEY, customer TEXT, source TEXT);
CREATE TABLE IF NOT EXISTS column_mappings(
  source_fingerprint TEXT PRIMARY KEY, mapping_json TEXT);
CREATE TABLE IF NOT EXISTS workspace_meta(
  key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS outbox(
  id INTEGER PRIMARY KEY AUTOINCREMENT, to_addr TEXT, subject TEXT, body TEXT,
  kind TEXT, ref_id TEXT, status TEXT, detail TEXT, created_at TEXT);
"""

class Repository:
    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        self._local = threading.local()
        conn = self.conn  # the creating thread's connection; builds the schema
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(payments)").fetchall()]
        if "references_json" not in cols:
            conn.execute("ALTER TABLE payments ADD COLUMN references_json TEXT DEFAULT '[]'")
        conn.commit()

    @property
    def conn(self):
        """One SQLite connection per thread. A single shared connection
        corrupts under concurrent requests (sqlite3.InterfaceError: bad
        parameter or other API misuse) because cursors interleave on it.
        WAL mode plus a busy timeout makes per-thread connections to the
        same file safe, and in-memory repositories stay inside the one
        request thread that created them."""
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(self.path, check_same_thread=False)
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA busy_timeout=5000")
            self._local.conn = c
        return c

    def _x(self, sql, params=()):
        with self._lock:
            cur = self.conn.execute(sql, params)
            self.conn.commit()
            return cur

    def add_invoice(self, inv):
        self._x("INSERT OR REPLACE INTO invoices VALUES (?,?,?,?,?,?,?,?,?,?, 'OPEN')",
                (inv.invoice_id, inv.customer, inv.subsidiary, inv.gross_cents, inv.currency,
                 inv.po_number, inv.discount_rate, inv.age_days, inv.due_in_days, inv.predicted_delay_days))

    def add_payment(self, pay, fingerprint=""):
        self._x("INSERT OR REPLACE INTO payments(payment_id, payer_raw, payer_customer, amount_cents,"
                " currency, claimed_deduction_cents, deduction_reason_raw, pod_verified_clean,"
                " remittance_text, fingerprint, references_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (pay.payment_id, pay.payer_raw, None, pay.amount_cents, pay.currency,
                 pay.claimed_deduction_cents, pay.deduction_reason_raw,
                 1 if pay.pod_verified_clean else 0, pay.remittance_text, fingerprint,
                 json.dumps(list(getattr(pay, "references", []) or []))))

    def all_payments(self):
        rows = self.conn.execute(
            "SELECT payment_id, payer_raw, amount_cents, currency, claimed_deduction_cents,"
            " deduction_reason_raw, pod_verified_clean, remittance_text, references_json"
            " FROM payments ORDER BY rowid").fetchall()
        from domain import Payment
        out = []
        for r in rows:
            try: refs = json.loads(r[8] or "[]")
            except Exception: refs = []
            out.append(Payment(payment_id=r[0], payer_raw=r[1], amount_cents=r[2], currency=r[3],
                               claimed_deduction_cents=r[4], deduction_reason_raw=r[5] or "",
                               pod_verified_clean=bool(r[6]), remittance_text=r[7] or "",
                               references=refs))
        return out

    def pending_payments(self):
        """Staged payments no run has touched yet (not in matches or exceptions)."""
        done = {r[0] for r in self.conn.execute("SELECT payment_id FROM matches").fetchall()}
        done |= {r[0] for r in self.conn.execute("SELECT payment_id FROM exceptions").fetchall()}
        return [p for p in self.all_payments() if p.payment_id not in done]

    def clear_workspace(self):
        with self._lock:
            for t in ("invoices", "payments", "runs", "run_steps", "matches", "exceptions", "workspace_meta"):
                self.conn.execute(f"DELETE FROM {t}")
            self.conn.commit()

    def set_meta(self, key, value):
        self._x("INSERT OR REPLACE INTO workspace_meta VALUES (?,?)", (key, json.dumps(value)))

    def get_meta(self, key):
        r = self.conn.execute("SELECT value FROM workspace_meta WHERE key=?", (key,)).fetchone()
        if not r: return None
        try: return json.loads(r[0])
        except Exception: return None

    def open_invoices(self, customer=None, subsidiary=None):
        q = "SELECT invoice_id, customer, subsidiary, gross_cents, currency, po_number, discount_rate, age_days, due_in_days, predicted_delay_days FROM invoices WHERE status='OPEN'"
        rows = self.conn.execute(q).fetchall()
        from domain import Invoice
        out = []
        for r in rows:
            inv = Invoice(invoice_id=r[0], customer=r[1], subsidiary=r[2], gross_cents=r[3], currency=r[4],
                          po_number=r[5], discount_rate=r[6], age_days=r[7], due_in_days=r[8], predicted_delay_days=r[9])
            if customer and inv.customer != customer: continue
            if subsidiary and inv.subsidiary != subsidiary: continue
            out.append(inv)
        return out

    def all_invoices(self):
        """Every invoice in the workspace, any status (open or settled)."""
        rows = self.conn.execute(
            "SELECT invoice_id, customer, subsidiary, gross_cents, currency, po_number,"
            " discount_rate, age_days, due_in_days, predicted_delay_days, status FROM invoices").fetchall()
        from domain import Invoice
        return [Invoice(invoice_id=r[0], customer=r[1], subsidiary=r[2], gross_cents=r[3],
                        currency=r[4], po_number=r[5], discount_rate=r[6], age_days=r[7],
                        due_in_days=r[8], predicted_delay_days=r[9]) for r in rows]

    def settle_invoices(self, invoice_ids):
        """Mark invoices settled (posted against an approved match). They
        leave the open ledger, the forecast and future candidate pools."""
        for iid in invoice_ids:
            self._x("UPDATE invoices SET status='SETTLED' WHERE invoice_id=?", (iid,))

    def create_run(self, run_id, idem_key, kind, policy_json, created_at):
        self._x("INSERT INTO runs VALUES (?,?,?,?,?,?,NULL)",
                (run_id, idem_key, kind, 'RUNNING', policy_json, created_at))
    def finish_run(self, run_id, status, finished_at):
        self._x("UPDATE runs SET status=?, finished_at=? WHERE run_id=?", (status, finished_at, run_id))
    def find_run_by_idempotency(self, key):
        r = self.conn.execute("SELECT run_id, status FROM runs WHERE idempotency_key=?", (key,)).fetchone()
        return r
    def steps_for_run(self, run_id):
        rows = self.conn.execute(
            "SELECT agent_name, status, latency_ms, evidence_json, confidence FROM run_steps "
            "WHERE run_id=? ORDER BY id", (run_id,)).fetchall()
        return [{"agent": r[0], "status": r[1], "latency_ms": r[2],
                 "evidence": json.loads(r[3]) if r[3] else {}, "confidence": r[4]} for r in rows]
    def add_step(self, run_id, agent, status, latency_ms, evidence, confidence):
        self._x("INSERT INTO run_steps(run_id, agent_name, status, latency_ms, evidence_json, confidence) VALUES (?,?,?,?,?,?)",
                (run_id, agent, status, latency_ms, json.dumps(evidence), confidence))
    def add_match(self, match_id, run_id, payment_id, status, solver, residual, confidence, result):
        self._x("INSERT INTO matches VALUES (?,?,?,?,?,?,?,?)",
                (match_id, run_id, payment_id, status, solver, residual, confidence, json.dumps(result)))
    def add_exception(self, run_id, payment_id, kind, severity, action, detail):
        self._x("INSERT INTO exceptions(run_id, payment_id, kind, severity, recommended_action, detail_json) VALUES (?,?,?,?,?,?)",
                (run_id, payment_id, kind, severity, action, json.dumps(detail)))
    def audit(self, actor, action, entity, entity_id, payload, ts):
        self._x("INSERT INTO audit_log(actor, action, entity, entity_id, payload_json, created_at) VALUES (?,?,?,?,?,?)",
                (actor, action, entity, entity_id, json.dumps(payload), ts))
    def exceptions_for_run(self, run_id):
        rows = self.conn.execute("SELECT payment_id, kind, severity, recommended_action, detail_json, status FROM exceptions WHERE run_id=?", (run_id,)).fetchall()
        return [{"payment_id": r[0], "kind": r[1], "severity": r[2], "recommended_action": r[3], "detail": json.loads(r[4]), "status": r[5]} for r in rows]
    def matches_for_run(self, run_id):
        rows = self.conn.execute("SELECT payment_id, status, solver, residual_cents, confidence, result_json FROM matches WHERE run_id=?", (run_id,)).fetchall()
        return [{"payment_id": r[0], "status": r[1], "solver": r[2], "residual_cents": r[3], "confidence": r[4], "result": json.loads(r[5])} for r in rows]

    def list_runs(self, limit=20):
        rows = self.conn.execute(
            "SELECT r.run_id, r.kind, r.status, r.created_at, r.finished_at, "
            "(SELECT COUNT(*) FROM matches m WHERE m.run_id=r.run_id) AS match_count, "
            "(SELECT COUNT(*) FROM matches m WHERE m.run_id=r.run_id AND m.status='AUTO_POSTED') AS auto_posted, "
            "(SELECT COUNT(*) FROM exceptions e WHERE e.run_id=r.run_id) AS exception_count, "
            "(SELECT COUNT(*) FROM (SELECT payment_id FROM matches WHERE run_id=r.run_id UNION SELECT payment_id FROM exceptions WHERE run_id=r.run_id)) AS payment_count "
            "FROM runs r ORDER BY r.created_at DESC LIMIT ?", (limit,)).fetchall()
        return [{"run_id": r[0], "kind": r[1], "status": r[2], "created_at": r[3], "finished_at": r[4],
                 "matches": r[5], "auto_posted": r[6], "exceptions": r[7], "payments": r[8]} for r in rows]


    def get_match(self, match_id):
        row = self.conn.execute("SELECT match_id, run_id, payment_id, status, result_json FROM matches WHERE match_id=?",
                                (match_id,)).fetchone()
        if not row: return None
        return {"match_id": row[0], "run_id": row[1], "payment_id": row[2], "status": row[3],
                "result": json.loads(row[4])}

    def latest_match_for_payment(self, payment_id):
        row = self.conn.execute(
            "SELECT match_id, run_id, payment_id, status, result_json FROM matches "
            "WHERE payment_id=? ORDER BY rowid DESC LIMIT 1", (payment_id,)).fetchone()
        if not row: return None
        return {"match_id": row[0], "run_id": row[1], "payment_id": row[2],
                "status": row[3], "result": json.loads(row[4])}

    def update_match(self, match_id, status, result):
        self._x("UPDATE matches SET status=?, result_json=? WHERE match_id=?",
                (status, json.dumps(result), match_id))

    def list_proposed(self, limit=50):
        rows = self.conn.execute(
            "SELECT match_id, run_id, payment_id, confidence, result_json FROM matches "
            "WHERE status='PROPOSED' ORDER BY rowid DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for r in rows:
            res = json.loads(r[4])
            eq = (res.get("derivation") or {}).get("equation") or {}
            out.append({"match_id": r[0], "run_id": r[1], "payment_id": r[2], "confidence": r[3],
                        "amount_cents": eq.get("payment_cents"),
                        "invoices": [l.get("invoice_id") for l in res.get("lines", [])],
                        "decision_reason": res.get("decision_reason")})
        return out

    def add_outbox(self, to_addr, subject, body, kind, ref_id, status, detail, ts):
        cur = self._x("INSERT INTO outbox(to_addr, subject, body, kind, ref_id, status, detail, created_at) VALUES (?,?,?,?,?,?,?,?)",
                      (to_addr, subject, body, kind, ref_id, status, detail, ts))
        return cur.lastrowid
    def list_outbox(self, limit=50):
        rows = self.conn.execute(
            "SELECT id, to_addr, subject, kind, ref_id, status, detail, created_at FROM outbox "
            "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"id": r[0], "to": r[1], "subject": r[2], "kind": r[3], "ref_id": r[4],
                 "status": r[5], "detail": r[6], "created_at": r[7]} for r in rows]

    def audit_list(self, limit=100):
        rows = self.conn.execute(
            "SELECT actor, action, entity, entity_id, payload_json, created_at FROM audit_log "
            "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"actor": r[0], "action": r[1], "entity": r[2], "entity_id": r[3],
                 "payload": json.loads(r[4]), "created_at": r[5]} for r in rows]
