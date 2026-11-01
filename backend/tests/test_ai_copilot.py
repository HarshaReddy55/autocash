import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))
from ai import deterministic_parse, parse_remittance, GeminiClient
from domain import Invoice, Payment, Policy
from repository import Repository
from batch import run_batch
from copilot import answer

TEXT = """Hi team, remittance from Apex Manufacturing Inc. Wire of $200.00 against INV-1023 and INV 1024.
Less deduction $50.00 for shortage on delivery. PO-77 referenced. Thanks"""

def test_deterministic_parse():
    f = deterministic_parse(TEXT)
    assert f["amount_cents"] == 20000, f
    assert "INV-1023" in f["invoice_refs"] and "INV-1024" in f["invoice_refs"]
    assert f["deduction_cents"] == 5000 and f["deduction_reason"] == "shortage"

def test_gemini_path_and_verifier_flags_unknown_ref():
    fake = lambda payload: {"candidates": [{"content": {"parts": [{"text":
        '{"payer":"Apex Manufacturing Corp","amount_cents":20000,"invoice_refs":["INV-1023","INV-9999"],"po_refs":["PO-77"],"deduction_cents":5000,"deduction_reason":"shortage"}'}]}}]}
    out = parse_remittance(TEXT, known_invoice_ids={"INV-1023", "INV-1024"}, known_po_numbers={"PO-77"},
                           client=GeminiClient(api_key="test", transport=fake))
    assert out["source"] == "gemini"
    assert out["verification"]["verified"] is False
    assert any("INV-9999" in i for i in out["verification"]["issues"])

def test_gemini_garbage_falls_back():
    fake = lambda payload: {"candidates": [{"content": {"parts": [{"text": "not json"}]}}]}
    out = parse_remittance(TEXT, client=GeminiClient(api_key="test", transport=fake))
    assert out["source"] == "deterministic_fallback" and out["degraded"] is True
    assert out["fields"]["amount_cents"] == 20000

def test_copilot_grounded_and_refuses():
    repo = Repository(os.path.join(tempfile.mkdtemp(), "c.db"))
    repo.add_invoice(Invoice("INV-1", "Apex Manufacturing", "Apex Manufacturing", 12000, age_days=40))
    repo.add_invoice(Invoice("INV-2", "Apex Manufacturing", "Apex Manufacturing", 8000, age_days=5))
    run_batch(repo, [Payment("P1", "Apex Manufacturing", 20000), Payment("P9", "TransGlobal Trading", 77700)], Policy(), idempotency_key="ck1")
    a = answer(repo, "Why was P9 not matched?")
    assert "P9" in a["answer"] and a["citations"]
    a2 = answer(repo, "What is the CEO's home address?")
    assert "does not contain" in a2["answer"]
    a3 = answer(repo, "What is the touchless automation rate?")
    assert "Touchless rate" in a3["answer"]
