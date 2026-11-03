# AutoCash - Deployment Guide
AutoCash product pack, document 5 of 8. Previous: Implementation Guide.
Next: AWS Deployment Runbook.
This guide describes the deployment model that applies on any host.
The step-by-step runbook for the live reference deployment (AWS ECS
Express Mode) is document 6 of this pack.

## 1. The unit of deployment
One container image, built from the repository Dockerfile in two
stages: the Rust kernel is compiled first, then placed into the Python
application image together with the Tesseract OCR engine. The image
serves the API and the frontend from one process on port 8080. The
full automated test suite (134 tests, plus the Rust kernel tests) runs
in continuous integration and gates the image build: a failing suite
means no image is produced.

## 2. Configuration
All configuration is by environment variable. Nothing is configured in
code, and no secret is stored in the repository.

- AUTOCASH_DATA_DIR: where tenant and workspace databases live. Point
  it at a persistent volume for any deployment whose data must survive.
- AUTOCASH_BOOTSTRAP_KEY: set it for secured mode (tenant API keys are
  then enforced). Leave it unset only for a demonstration on synthetic
  data; the health endpoint labels that posture as demo-open.
- GEMINI_API_KEY: optional. Without it, no external AI call is made
  and parsing runs on the deterministic parser, labelled as such.
- GEMINI_MODEL: set this explicitly whenever a Gemini key is used. If
  it is absent, the application uses a built-in default model, which
  may be a slower model than your account should use; the failure mode
  is a request that hangs until a timeout instead of a clear error.
  The reference deployment uses gemini-3.5-flash-lite, a low-latency
  model, because the hosting platform ends any request at about sixty
  seconds and the product's own AI timeout is set below that ceiling
  so a slow AI answer always degrades gracefully instead of failing
  the page.
- AUTOCASH_RATE_LIMIT_PER_MIN: per-key request limit, default 300.
- Thread limits (OMP_NUM_THREADS and peers): set to 1 on small tasks
  so the numerical libraries do not oversubscribe a fractional CPU.

## 3. Data and what resets
Tenant and workspace state lives in SQLite files under
AUTOCASH_DATA_DIR. On a host with an ephemeral filesystem (the
demonstration deployment is one), that data resets when the task is
replaced or the service is redeployed. This is accepted for the
demonstration and stated openly: the demo case reloads in one action
and the full demonstration is reproducible in under a minute. For a
paying pilot, the same image runs with the data directory on a
persistent volume, or the tenant databases move to a managed Postgres;
that migration is the first paid-pilot engineering task and is named
as such in the Implementation Guide.

## 4. Shipping an update
1. Commit and push through GitHub Desktop. The repository is copied,
   never surgically edited on the server.
2. Continuous integration runs the test suite, then builds and pushes
   the image.
3. Update the service on the host (on ECS, one Update service action).
4. Verify what is actually served, not what was intended: the page's
   asset URLs carry version stamps, and a changed stamp proves the new
   build is live. If a browser still shows the old version afterwards,
   it is the browser cache; a private window settles the question.

## 5. Routes evaluated for the reference deployment
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

## 6. Demo posture, stated plainly
The shared demonstration link runs demo-open on synthetic data, with
per-session workspaces so visitors do not disturb each other. No real
customer data should ever be placed behind a demo-open deployment.
The secured mode exists in the same build and is the only posture for
a pilot.
