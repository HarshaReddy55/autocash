# AutoCash - Implementation Guide
For a customer finance + IT team piloting AutoCash. Estimated pilot effort:
1 to 2 weeks part-time, dominated by data extraction, not software setup.

## 1. Deploy
Option A - Docker (recommended):
  docker build -t autocash .
  docker run -p 8080:8080 -v autocash-data:/app/data \
    -e AUTOCASH_BOOTSTRAP_KEY=<strong secret> \
    -e GEMINI_API_KEY=<optional, enables AI parsing> autocash
Option B - Cloud Run: use the included cloudbuild.yaml (service name and
region are configurable there); set the same env vars as secrets.
Option C - Local evaluation: Python 3.12 venv, pip install -r
backend/requirements.txt, uvicorn api:app --app-dir backend/app.

## 2. First-run setup (15 minutes)
1. POST /admin/tenants with the bootstrap key -> tenant_id.
2. POST /admin/tenants/{id}/keys for each role (admin, approver, analyst,
   viewer). Keys are shown once; store them in your secrets manager.
3. PUT /api/v1/policy with your thresholds (automation threshold, tolerance
   write-off limit, maker-checker value, dispute minimum recovery).
4. Verify /health shows auth: api-key, and /ready is green.

## 3. Data onboarding
- Open invoices: POST /api/v1/invoices/import with CSV text. Headers are
  auto-mapped (common synonyms recognised); unmapped or malformed rows are
  returned as quarantined errors with row numbers - nothing is silently
  dropped. Every import carries a content fingerprint for audit.
- Payments: submit via POST /api/v1/batches (API) - bank/lockbox file
  adapters are configured per customer during the pilot.
- Customer aliases: payer name variants are learned per tenant as analysts
  confirm matches (alias table ships in the tenant database).

## 4. Go-live checklist
- [ ] Policy thresholds signed off by AR manager (maker-checker value set)
- [ ] Pilot scope: one subsidiary / one bank account, 2 weeks of payments
- [ ] Baseline measured: current manual match rate and analyst hours
- [ ] Exception queue ownership assigned (daily review cadence)
- [ ] Gemini key configured OR deterministic mode accepted (product works
      fully without it; AI parsing is an enhancement, never a dependency)
- [ ] Success criteria agreed: touchless rate, residual dollars, exception
      ageing - measured from AutoCash run records, exported for review

## 5. Operations
- Logs: structured JSON per request with request_id; ship to your aggregator.
- Metrics: GET /metrics (Prometheus format). Alert on 5xx rate and p95
  latency (latency counters are cumulative per path in v1).
- Readiness: GET /ready checks control DB, data dir, model load.
- Backups: back up the data directory (one SQLite file per tenant plus the
  control DB). Restore = replace files and restart.
- Rate limits: AUTOCASH_RATE_LIMIT_PER_MIN per API key (default 300).
  In-memory in v1: exact for single-instance deployments.

## 6. Security notes
- API keys are SHA-256 hashed at rest; raw keys exist only at issuance.
- Tenant isolation is physical (separate database file per tenant).
- No payment data leaves the deployment except optional Gemini parsing
  calls (disable by leaving GEMINI_API_KEY unset; parsing falls back to
  the deterministic parser and flags degraded mode in its response).
- Audit log per tenant records actor, action and before/after for policy
  and run events.
