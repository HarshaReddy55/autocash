"""v13 surfacing: ERP documents from erp_sap, diagnostics, in-app docs,
and demo tenant switching with real database isolation."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
os.environ.setdefault("AUTOCASH_DATA_DIR", os.path.join(os.path.dirname(__file__), "api_data"))
from fastapi.testclient import TestClient
import api as api_mod

client = TestClient(api_mod.app)


def _seed_run(key):
    client.post("/api/v1/workspace/reset")
    client.post("/api/v1/cases/seed/load")
    ws = client.get("/api/v1/workspace").json()
    r = client.post("/api/v1/batches", json={
        "idempotency_key": key, "payments": ws["pending_payments"]})
    assert r.status_code == 200, r.text
    return r.json()


def test_erp_document_is_balanced_and_built_from_the_match():
    _seed_run("v13-erp-1")
    r = client.get("/api/v1/payments/P1/erp-document")
    assert r.status_code == 200, r.text
    d = r.json()["document"]
    assert d["balanced"] is True
    assert d["total_debits_cents"] == d["total_credits_cents"] > 0
    assert d["bapi_payload"]["DOCUMENTHEADER"]["DOCUMENT_TYPE"] == "DZ"
    assert d["status"] == "preview"  # nothing approved yet, no document number
    # P3 carries a dispute claim: the revrec accrual must ride along
    r3 = client.get("/api/v1/payments/P3/erp-document")
    assert r3.status_code == 200, r3.text
    acc = r3.json().get("revrec_accrual")
    assert acc and acc["balanced"] is True
    assert acc["journal"][0]["gl_account"] == "121500"


def test_erp_document_unknown_payment_404():
    assert client.get("/api/v1/payments/NOPE/erp-document").status_code == 404


def test_diagnostics_reports_kernel_and_suite():
    d = client.get("/api/v1/diagnostics").json()
    assert "present" in d["rust_kernel"]
    assert d["rust_kernel"]["equivalence_probe"]["status"] in (
        "pass", "fail", "kernel_absent")
    assert d["test_suite"]["module_count"] >= 15
    assert "test_rust_equivalence" in d["test_suite"]["modules"]
    assert "test_milp_solvers" in d["test_suite"]["modules"]
    assert "test_reference_engine" in d["test_suite"]["modules"]


def test_docs_list_and_read():
    d = client.get("/api/v1/docs").json()
    names = {x["name"] for x in d["docs"]}
    assert {"PRD.md", "ARCHITECTURE.md", "GO_TO_MARKET.md"} <= names
    r = client.get("/api/v1/docs/PRD.md")
    assert r.status_code == 200 and len(r.json()["markdown"]) > 500
    assert client.get("/api/v1/docs/NOPE.md").status_code == 404
    assert client.get("/api/v1/docs/requirements.txt").status_code == 404


def test_demo_tenant_switch_isolates_data():
    client.post("/api/v1/workspace/reset")
    client.post("/api/v1/cases/seed/load")
    assert len(client.get("/api/v1/invoices").json()) == 19
    eu = {"X-Tenant-Id": "demo-eu"}
    assert client.get("/api/v1/invoices", headers=eu).json() == []
    info = client.get("/api/v1/tenants/demo", headers=eu).json()
    assert info["switching_enabled"] is True and info["active"] == "demo-eu"
    assert {t["id"] for t in info["tenants"]} == {"demo", "demo-eu"}
    # an unknown tenant id falls back to the default demo tenant
    bad = client.get("/api/v1/tenants/demo", headers={"X-Tenant-Id": "acme"}).json()
    assert bad["active"] == "demo"
    # the default tenant still holds the seed case
    assert len(client.get("/api/v1/invoices").json()) == 19
