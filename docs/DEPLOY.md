# AutoCash - Deployment Guide
AutoCash product pack, document 5 of 8. Previous: Implementation Guide.
Next: AWS Deployment Runbook.
This guide describes the deployment model that applies on any host.
The step-by-step runbook for the live reference deployment (AWS ECS
Express Mode) is document 6 of this pack.

## 1. The unit of deployment
One container image, built from the repository Dockerfile in two
stages:

1. Stage 1 (rust:1.82-slim): compiles the Rust kernel in release mode.
2. Stage 2 (python:3.12-slim): installs the pinned dependencies from
   backend/requirements.txt and carries the application, the frontend,
   this document pack, the compiled kernel binary and the Tesseract
   OCR engine.

The image serves the API and the frontend from one process:

```bash
docker build -t autocash .
docker run -p 8080:8080 -v autocash-data:/app/data autocash
```

- Exposed port: 8080 (the server binds ${PORT:-8080}).
- Server command: uvicorn api:app --app-dir backend/app.
- Healthcheck: GET /ready on port 8080.
- The full automated test suite (134 tests across 29 modules, plus
  the 4 Rust kernel tests) runs in CI and gates the image build: a
  failing suite means no image is produced.

## 2. Runtime configuration variables
All configuration is by environment variable. Nothing is configured in
code, and no secret is stored in the repository.

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| AUTOCASH_DATA_DIR | backend/data, relative to the app | Where tenant and workspace SQLite databases live; point it at a persistent volume for any deployment whose data must survive |
| AUTOCASH_BOOTSTRAP_KEY | Unset | Set for secured mode, where tenant API keys are enforced; unset means the labelled demo-open posture |
| AUTOCASH_KERNEL_BIN | Unset | Path to the compiled Rust kernel binary; without it, plain payments are decided by the MILP alone |
| AUTOCASH_DOCS_DIR | Unset | Overrides the location this document pack is served from |
| AUTOCASH_RATE_LIMIT_PER_MIN | 300 | Per-API-key request limit |
| GEMINI_API_KEY | Unset | Enables AI remittance parsing and drafting; unset means no external AI call is made at all |
| GEMINI_MODEL | Built-in default | Set explicitly whenever a key is used (see the warning below); the reference deployment uses gemini-3.5-flash-lite |
| GEMINI_TIMEOUT_S | 40 | Client timeout for AI calls, set below the hosting platform's request ceiling |
| AUTOCASH_SMTP_HOST, AUTOCASH_SMTP_PORT | Unset, 587 | Mail server for live sending |
| AUTOCASH_SMTP_USER, AUTOCASH_SMTP_PASSWORD | Unset | Mail credentials; the password is redacted in diagnostics |
| AUTOCASH_MAIL_FROM | Unset | Sender address for outbound mail |
| AUTOCASH_SMTP_TLS | On | TLS for the SMTP connection; set to 0 to disable |
| OMP_NUM_THREADS and peers | Unset | Set to 1 on small tasks so the numerical libraries do not oversubscribe a fractional CPU |

One warning, learned in production: set GEMINI_MODEL explicitly. If it
is absent, the application uses a built-in default model, which may be
a slower model than your account should use; the failure mode is a
request that hangs until a timeout instead of a clear error. The
reference deployment uses gemini-3.5-flash-lite, a low-latency model,
because the hosting platform ends any request at about sixty seconds
and the product's own AI timeout (40 seconds) sits below that ceiling,
so a slow AI answer always degrades gracefully to the deterministic
parser instead of failing the page.

## 3. Local workstation deployment
For evaluation without Docker:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

# Optional: build the Rust kernel for the subset-sum accelerator
cd rust-kernel && cargo build --release && cd ..
export AUTOCASH_KERNEL_BIN=$PWD/rust-kernel/target/release/autocash-kernel

uvicorn api:app --app-dir backend/app --port 8080
```

Open http://localhost:8080 for the fourteen-screen workspace, load the
demo case from Use Cases, and execute the run. Without the kernel the
product is fully functional; the kernel only accelerates one step, and
the diagnostics view states which mode the system is in.

## 4. Data and what resets
Tenant and workspace state lives in SQLite files under
AUTOCASH_DATA_DIR (WAL mode; one file per tenant, one per workspace
session). On a host with an ephemeral filesystem (the demonstration
deployment is one), that data resets when the task is replaced or the
service is redeployed. This is accepted for the demonstration and
stated openly: the demo case reloads in one action and the full
demonstration is reproducible in under a minute. For a paying pilot,
the same image runs with the data directory on a persistent volume, or
the tenant databases move to a managed Postgres; that migration is the
first paid-pilot engineering task and is named as such in the
Implementation Guide.

## 5. Shipping an update
1. Copy the changed files into the repository and commit through
   GitHub Desktop; push to main. (Bundles for this project never
   rename or delete files, so a copy-merge is always clean.)
2. CI runs the test suite first; only a green suite builds and pushes
   the image.
3. Update the service on the host (on ECS, one Update service action).
4. Verify what is actually served, not what was intended: the page's
   asset URLs carry version stamps, and a changed stamp proves the new
   build is live. If a browser still shows the old version afterwards,
   it is the browser cache; a private window settles the question.

## 6. Routes evaluated for the reference deployment
The reference deployment had one hard constraint: zero out-of-pocket
cost, no card and no prepayment. The routes below were checked against
it in Oct and Nov 2026.

- Google Cloud Run: technically straightforward, and a runbook existed
  for it. Rejected: enabling it required a billing prepayment the
  project would not make. Cost discipline outranked convenience.
- Railway, Hugging Face Spaces, Render (free tier): each fell short on
  at least one of always-on availability, memory for the ML stack, or
  a filesystem story for the tenant databases.
- AWS ECS Express Mode: chosen. It runs on account credits (about
  $28 per month at the reference sizing of 0.25 vCPU and 1 GB, with
  autoscaling capped at 3 tasks as a credit guard), provides HTTPS
  and a public URL from one image, and needs no prepayment. The full
  runbook is document 6.

For a customer deployment, the constraint changes and so may the
answer: the image is host-agnostic, and any Docker host with a
persistent volume is a valid target.

## 7. Demo posture, stated plainly
The shared demonstration link runs demo-open on synthetic data, with
per-session workspaces so visitors do not disturb each other. No real
customer data should ever be placed behind a demo-open deployment.
The secured mode exists in the same build and is the only posture for
a pilot.

Version 3.0 | 3 Nov 2026 | Owner: C. Harsha Vardhana Reddy
