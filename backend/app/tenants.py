"""Tenancy + API keys + RBAC.
Isolation model: one SQLite database file per tenant (data/<tenant_id>.db).
Keys are stored only as SHA-256 hashes; the raw key is returned once at issue.
Roles: admin > approver > analyst > viewer (capability sets, not hierarchy math)."""
import hashlib, os, secrets, sqlite3, time, json

ROLE_CAPS = {
    "viewer": {"read"},
    "analyst": {"read", "run", "parse"},
    "approver": {"read", "run", "parse", "approve"},
    "admin": {"read", "run", "parse", "approve", "admin"},
}

def _hash(key): return hashlib.sha256(key.encode()).hexdigest()

class TenantStore:
    def __init__(self, base_dir):
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)
        self.conn = sqlite3.connect(os.path.join(base_dir, "_control.db"), check_same_thread=False)
        self.conn.execute("CREATE TABLE IF NOT EXISTS tenants (tenant_id TEXT PRIMARY KEY, name TEXT, created_at REAL)")
        self.conn.execute("""CREATE TABLE IF NOT EXISTS api_keys (key_hash TEXT PRIMARY KEY, tenant_id TEXT,
                             role TEXT, label TEXT, created_at REAL, revoked INTEGER DEFAULT 0)""")
        self.conn.execute("CREATE TABLE IF NOT EXISTS tenant_policies (tenant_id TEXT PRIMARY KEY, policy_json TEXT)")
        self.conn.commit()

    def create_tenant(self, name):
        tid = "t_" + secrets.token_hex(4)
        self.conn.execute("INSERT INTO tenants VALUES (?,?,?)", (tid, name, time.time())); self.conn.commit()
        return tid

    def tenant_exists(self, tid):
        return self.conn.execute("SELECT 1 FROM tenants WHERE tenant_id=?", (tid,)).fetchone() is not None

    def issue_key(self, tenant_id, role, label=""):
        if role not in ROLE_CAPS: raise ValueError(f"unknown role {role}")
        raw = "ack_" + secrets.token_urlsafe(32)
        self.conn.execute("INSERT INTO api_keys VALUES (?,?,?,?,?,0)", (_hash(raw), tenant_id, role, label, time.time()))
        self.conn.commit()
        return raw

    def resolve(self, raw_key):
        if not raw_key: return None
        row = self.conn.execute("SELECT tenant_id, role FROM api_keys WHERE key_hash=? AND revoked=0",
                                (_hash(raw_key),)).fetchone()
        return {"tenant_id": row[0], "role": row[1]} if row else None

    def revoke(self, raw_key):
        self.conn.execute("UPDATE api_keys SET revoked=1 WHERE key_hash=?", (_hash(raw_key),)); self.conn.commit()

    def set_policy(self, tenant_id, policy_dict):
        self.conn.execute("INSERT OR REPLACE INTO tenant_policies VALUES (?,?)",
                          (tenant_id, json.dumps(policy_dict))); self.conn.commit()

    def get_policy(self, tenant_id):
        row = self.conn.execute("SELECT policy_json FROM tenant_policies WHERE tenant_id=?", (tenant_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def db_path(self, tenant_id):
        return os.path.join(self.base_dir, f"{tenant_id}.db")
