"""AI layer: Gemini client wrapper + deterministic parser + verifier.
Design rule (from ARCHITECTURE.md): LLM proposes, deterministic code disposes.
Every AI feature has a deterministic fallback; degraded mode is explicit."""
import os, re, json
import httpx

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
PARSE_SCHEMA_HINT = ('Return ONLY JSON with keys: payer (string), amount_cents (int), '
                     'invoice_refs (list of strings), po_refs (list of strings), '
                     'deduction_cents (int), deduction_reason (string)')

class GeminiClient:
    def __init__(self, api_key=None, transport=None):
        self.api_key = api_key if api_key is not None else os.environ.get("GEMINI_API_KEY", "")
        self.transport = transport  # injectable for tests
    @property
    def available(self): return bool(self.api_key)
    def generate_json(self, prompt):
        if not self.available:
            raise RuntimeError("GEMINI_API_KEY not configured")
        payload = {"contents": [{"parts": [{"text": prompt}]}],
                   "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}
        if self.transport is not None:
            resp = self.transport(payload)
            text = resp["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)
        with httpx.Client(timeout=30) as c:
            r = c.post(GEMINI_URL, params={"key": self.api_key}, json=payload)
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)

INV_RE = re.compile(r"\bINV[- ]?\d+\b", re.I)
PO_RE = re.compile(r"\bPO[- ]?\d+\b", re.I)
AMT_RES = [re.compile(r"\$\s*([0-9,]+(?:\.[0-9]{1,2})?)"),
           re.compile(r"(?:USD|INR|Rs\.?)\s*([0-9,]+(?:\.[0-9]{1,2})?)", re.I),
           re.compile(r"\b([0-9,]+\.[0-9]{2})\b")]

def _cents(s): return int(round(float(s.replace(",", "")) * 100))

def deterministic_parse(text):
    invs = sorted(set(m.group(0).upper().replace(" ", "-") for m in INV_RE.finditer(text)))
    invs = [i if i.startswith("INV-") else "INV-" + i[3:] for i in invs]
    pos = sorted(set(m.group(0).upper().replace(" ", "-") for m in PO_RE.finditer(text)))
    pos = [p if p.startswith("PO-") else "PO-" + p[2:] for p in pos]
    amounts = []
    for rx in AMT_RES:
        amounts += [_cents(m.group(1)) for m in rx.finditer(text) if m.group(1)]
    amount = max(amounts) if amounts else 0
    ded = 0; reason = ""
    low = text.lower()
    dm = re.search(r"deduct[a-z]*[^0-9$]*\$?\s*([0-9,]+(?:\.[0-9]{2})?)", low)
    if dm: ded = _cents(dm.group(1))
    for kw in ("shortage", "damaged", "pricing", "promo", "freight", "tax"):
        if kw in low: reason = kw; break
    payer = ""
    pm = re.search(r"(?:from|payer|remitter)[:\s]+([A-Z][A-Za-z& ]{2,30})", text)
    if pm: payer = pm.group(1).strip()
    return {"payer": payer, "amount_cents": amount, "invoice_refs": invs, "po_refs": pos,
            "deduction_cents": ded, "deduction_reason": reason}

def verify_parse(parsed, known_invoice_ids, known_po_numbers):
    issues = []
    for ref in parsed.get("invoice_refs", []):
        if known_invoice_ids and ref not in known_invoice_ids:
            issues.append(f"invoice reference {ref} not found in open ledger")
    for ref in parsed.get("po_refs", []):
        if known_po_numbers and ref not in known_po_numbers:
            issues.append(f"PO reference {ref} not found in open ledger")
    if not parsed.get("amount_cents"):
        issues.append("no payment amount extracted")
    return {"verified": len(issues) == 0, "issues": issues}

def parse_remittance(text, known_invoice_ids=None, known_po_numbers=None, client=None):
    client = client or GeminiClient()
    source, degraded, fields = "deterministic", False, None
    if client.available:
        try:
            out = client.generate_json(f"Extract remittance fields from this text. {PARSE_SCHEMA_HINT}\n\nTEXT:\n{text}")
            required = {"payer", "amount_cents", "invoice_refs", "po_refs", "deduction_cents", "deduction_reason"}
            if not required.issubset(set(out.keys())):
                raise ValueError("schema incomplete")
            fields, source = out, "gemini"
        except Exception as e:
            fields, degraded = deterministic_parse(text), True
            source = "deterministic_fallback"
    else:
        fields, degraded = deterministic_parse(text), True
    v = verify_parse(fields, known_invoice_ids or set(), known_po_numbers or set())
    return {"fields": fields, "source": source, "degraded": degraded, "verification": v}
