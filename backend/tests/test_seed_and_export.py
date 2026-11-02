"""v27: the export bundle refuses an empty workspace, and the Capture
Agent's auto-seed endpoint creates exactly the missing referenced
invoices at evidence-backed amounts - never invented ones."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
os.environ.setdefault("AUTOCASH_DATA_DIR", os.path.join(os.path.dirname(__file__), "api_data"))
from fastapi.testclient import TestClient
import api as api_mod

client = TestClient(api_mod.app, raise_server_exceptions=False)


def test_export_bundle_refuses_a_workspace_with_no_run():
    client.post("/api/v1/workspace/reset")
    r = client.get("/api/v1/export/bundle")
    assert r.status_code == 409, r.text
    client.post("/api/v1/cases/seed/load")
    r = client.get("/api/v1/export/bundle")
    assert r.status_code == 409, r.text  # v31: staged is not a run - nothing to export yet
    client.post("/api/v1/workspace/run")
    r = client.get("/api/v1/export/bundle")
    assert r.status_code == 200, r.text


def test_parse_reports_unknown_refs_as_data():
    client.post("/api/v1/workspace/reset")
    client.post("/api/v1/cases/seed/load")
    r = client.post("/api/v1/parse", json={
        "text": "Please apply $1,000.00 to invoice INV-7001. Remittance from Acme Corp."})
    assert r.status_code == 200, r.text
    v = r.json()["verification"]
    assert v["verified"] is False
    assert v["unknown_refs"] == ["INV-7001"], v


def test_seed_single_ref_at_the_wire_amount_then_it_matches():
    client.post("/api/v1/workspace/reset")
    client.post("/api/v1/cases/seed/load")
    r = client.post("/api/v1/invoices/seed-referenced", json={
        "refs": ["INV-7001"], "payer": "Acme Corp", "wire_amount_cents": 100000,
        "remittance_text": "Please apply $1,000.00 to invoice INV-7001."})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["seeded"] == [{"invoice_id": "INV-7001", "gross_cents": 100000}]
    assert body["unresolved"] == []
    inv = client.get("/api/v1/invoices").json()
    assert any(i["invoice_id"] == "INV-7001" and i["gross_cents"] == 100000 for i in inv)


def test_seed_multi_ref_uses_amounts_listed_in_the_text():
    client.post("/api/v1/workspace/reset")
    r = client.post("/api/v1/invoices/seed-referenced", json={
        "refs": ["INV-7001", "INV-7002", "INV-7003"], "payer": "Beta LLC",
        "wire_amount_cents": 999999,
        "remittance_text": "INV-7001 $250.00\nINV-7002 $750.00\nTotal enclosed."})
    body = r.json()
    seeded = {s["invoice_id"]: s["gross_cents"] for s in body["seeded"]}
    assert seeded == {"INV-7001": 25000, "INV-7002": 75000}, body
    assert body["unresolved"] == ["INV-7003"], body


def test_seed_skips_refs_already_in_the_ledger():
    client.post("/api/v1/workspace/reset")
    client.post("/api/v1/cases/seed/load")
    r = client.post("/api/v1/invoices/seed-referenced", json={
        "refs": ["INV-1001"], "payer": "Apex", "wire_amount_cents": 500})
    body = r.json()
    assert body["seeded"] == [] and body["skipped_existing"] == ["INV-1001"]
