# AutoCash - Implementation Guide
AutoCash product pack, document 4 of 8. Previous: Architecture and
System Design. Next: Deployment Guide.
For a customer finance and IT team piloting AutoCash. Estimated pilot
effort: one to two weeks part-time, dominated by data extraction, not
software setup.

## 1. Deploy the service
Option A - Docker (recommended). One image contains the application, the
Rust kernel and the OCR engine:
  docker build -t autocash .
  docker run -p 8080:8080 -v autocash-data:/app/data \
    -e AUTOCASH_BOOTSTRAP_KEY=<strong secret> \
    -e GEMINI_API_KEY=<optional, enables AI parsing> \
    -e GEMINI_MODEL=gemini-3.5-flash-lite autocash
Option B - AWS ECS: the reference production deployment is documented
step by step in the AWS Deployment Runbook (document 6 of this pack).
Option C - Local evaluation: Python 3.12, a virtual environment,
pip install -r backend/requirements.txt, then run
uvicorn api:app --app-dir backend/app.

Two configuration points matter. First, set GEMINI_MODEL explicitly:
if it is absent, the application falls back to a built-in default that
may not suit your account, and the failure mode is a slow answer rather
than a clear error. Second, decide the posture. With a bootstrap key
set, the service is secured and every call needs a tenant API key.
Without one, it runs in a demo-open posture that the health endpoint
labels as such; use that only for demonstrations on synthetic data.

## 2. First-run setup (about 15 minutes)
1. Create the tenant: POST /admin/tenants with the bootstrap key.
   The response carries the tenant_id.
2. Issue keys: POST /admin/tenants/{tenant_id}/keys, one per role
   (admin, approver, analyst, viewer). Each key is shown once. Store
   them in your secrets manager; only their hashes are kept.
3. Set policy: PUT /api/v1/policy with your thresholds: the automation
   confidence threshold, the tolerance write-off ceiling, the
   maker-checker value above which a second person must approve, and
   the minimum expected recovery for an automatic dispute.
4. Verify: GET /health should report the secured posture, and
   GET /ready should be green.

## 3. Data onboarding
- Open invoices: POST /api/v1/invoices/import with CSV text, or use the
  Upload Center in the interface. Common column synonyms are recognised
  automatically. Rows that cannot be mapped or validated are returned
  as quarantined errors with row numbers; nothing is silently dropped.
  Every import carries a content fingerprint for audit.
- Payments: stage them through the Upload Center or the batch API
  (POST /api/v1/batches). Bank and lockbox file adapters are configured
  per customer during the pilot; they are not part of the standard
  build, and this guide does not pretend otherwise.
- Remittance files: PDF, PNG, JPG, plain text and email files can be
  uploaded for extraction. The extracted fields are verified against
  the open ledger before anything is staged.
- Customer aliases: payer name variants are stored per tenant as
  analysts confirm matches, and are applied to later runs.

## 4. How a pilot team works day to day
Each reviewer works in their own browser-session workspace, so parallel
review never collides. The rhythm is: load a case or the day's receipts
(staging changes nothing), execute the run, work the approvals queue,
review the SAP posting pack, and let the mail hub compose the dispute
claims, inquiries and confirmations from the run. The forecast and
collections views update from the residual ledger the run leaves
behind. At any point, the audit and SAP bundle can be exported for
review; the export is refused until a run exists, by design.

## 5. Go-live checklist
- [ ] Policy thresholds signed off by the AR manager, maker-checker
      value set deliberately, not left at the default
- [ ] Pilot scope fixed: one subsidiary, one bank account, two weeks
      of payments
- [ ] Baseline measured before the pilot: current manual match rate
      and analyst hours, so the result can be compared honestly
- [ ] Approvals queue ownership assigned, with a daily review cadence
- [ ] Gemini configured, or deterministic mode accepted in writing
      (the product works fully without the AI; parsing quality, not
      function, is what changes)
- [ ] Mail posture understood: until SMTP is configured, sends are
      recorded as recorded, not sent; connect the mailbox before any
      live sending
- [ ] Success criteria agreed in advance: touchless rate, residual
      dollars, exception ageing, measured from AutoCash run records
      and exported for review

## 6. Operations
- Logs: structured JSON per request, each with a request ID. Ship them
  to your aggregator.
- Metrics: GET /metrics in Prometheus format. Alert on the 5xx rate.
- Readiness and diagnosis: GET /ready for the readiness check, and the
  diagnostics endpoint (Agent Health screen) for dependency state,
  including the Rust kernel equivalence probe and the current AI mode
  and last AI error.
- Backups: back up the data directory (one SQLite file per tenant, one
  per workspace session, plus the control database). Restore means
  replacing the files and restarting.
- Rate limits: AUTOCASH_RATE_LIMIT_PER_MIN per API key, default 300.
  The limiter is in-memory, which is exact for a single-instance
  deployment; multi-instance limiting is part of the scaling design in
  the Architecture document and is labelled there as design.
- Updates: ship a new container image and update the service. Tenant
  data on a persistent volume survives; on an ephemeral demonstration
  host it resets, and the demo case reloads in one action.

## 7. Security notes
- API keys are SHA-256 hashed at rest; raw keys exist only at issuance.
- Tenant isolation is physical: a separate database file per tenant.
- No payment data leaves the deployment except the optional Gemini
  parsing calls. Leave GEMINI_API_KEY unset and no external AI call is
  made at all; parsing falls back to the deterministic parser and says
  so in its response.
- The audit log records actor, action and payload for approvals,
  decisions, policy changes and sends, and decision entries carry a
  content fingerprint that can be recomputed to prove they were not
  altered.
