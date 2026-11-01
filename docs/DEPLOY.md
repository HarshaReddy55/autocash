# AutoCash - Deployment Runbook (Google Cloud Run)

## What you need
- A Google Cloud project with billing enabled. (StartupMatrix already runs
  on Cloud Run in this account's ecosystem, so a working project exists;
  its project number appears in the StartupMatrix run.app URL.)
- This source bundle (autocash-source.zip) or the repo at ~/workspace/autocash.

## Route A - Cloud Shell (recommended, nothing to install)
1. Sign in to console.cloud.google.com with the account that owns the
   project. Select the project.
2. Open Cloud Shell (top-right terminal icon).
3. Upload autocash-source.zip via the Cloud Shell "Upload file" menu, then:
     unzip autocash-source.zip && cd autocash
4. Run:  PROJECT_ID=<your-project-id> ./deploy.sh
   The script enables APIs, creates the two secrets (prompting you for
   values - the bootstrap key is one you invent; the Gemini key is
   optional), grants secret access, builds with Cloud Build and deploys.
5. The script prints the service URL. Open it and check /ready shows
   "ready": true.

## Route B - Local gcloud
Install gcloud, run `gcloud auth login` (you complete the sign-in in your
browser), then the same ./deploy.sh command.

## First tenant (after deploy)
  curl -X POST <URL>/admin/tenants -H "X-API-Key: <bootstrap key>" \
       -H "Content-Type: application/json" -d '{"name":"Demo"}'
  curl -X POST <URL>/admin/tenants/<tenant_id>/keys \
       -H "X-API-Key: <bootstrap key>" -H "Content-Type: application/json" \
       -d '{"role":"admin","label":"founder"}'
Use the returned admin key in the UI/API from then on.

## Notes and limits
- Cloud Run is authenticated-by-default in this config only at the platform
  layer if you keep --no-allow-unauthenticated; the included cloudbuild.yaml
  deploys private. For a public demo link, redeploy with
  --allow-unauthenticated and rely on AutoCash API keys (the app enforces
  them once keys exist). For the referral demo, public URL + app keys is
  the pragmatic choice; say explicitly which posture you picked.
- Data: Cloud Run's filesystem is ephemeral. Tenant SQLite files live in
  /app/data inside the container and reset on redeploy. For a demo this is
  fine (re-seed in one click). For a paying pilot, mount Cloud Storage via
  gcsfuse or move to Cloud SQL - that migration is the first paid-pilot
  engineering task and is named as such in the implementation guide.
- Cost: Cloud Run scales to zero; a demo workload sits in the free tier in
  practice, but billing must be enabled on the project.

## Other Docker hosts (checked 31 Oct 2026, sources in research notes)
- Render (free, no card): render.yaml in this repo is a one-click Blueprint.
  512 MB RAM, spins down after 15 min idle, ephemeral disk. Best zero-cost
  demo link; memory is tight for the ML stack - if the service OOMs at
  startup, that is the known risk and Cloud Run with 1 GB is the fallback.
- Railway: $5 trial credit for 30 days, then a free plan with $1 monthly
  credit, no card for the trial. Deploys the Dockerfile directly.
- Fly.io: no free tier (short trial, card required); smallest always-on
  machine is a few dollars a month; fly.toml included, 1 GB RAM specified.
- SnapDeploy: free tier, no card, builds from a Dockerfile or tarball,
  sleeps after 15 min. Smaller, newer vendor - fine for a demo, not yet a
  production recommendation.
- VPS + Docker (e.g. Hetzner): a few dollars a month, full control, and the
  only cheap option with a persistent disk (tenant SQLite data survives).
  You operate the server yourself.
- Koyeb: free instance exists but sign-up now requires a card with a $29
  pre-authorisation hold - not recommended for a quick demo.

## Free-tier Google account (no subscription) - does it work?
Yes. Cloud Run needs no subscription or AI plan. The one requirement is a
project with billing enabled. A brand-new Google Cloud account normally
carries a free trial (credit for 90 days; Google asks for a card purely to
verify identity and does not charge unless you explicitly upgrade to a paid
billing account). Cloud Run also has an always-free monthly allowance
(requests, CPU and memory seconds) that a demo workload sits far inside, so
the referral demo costs nothing in practice. Cold start after idle is a few
seconds; for a zero-cold-start demo you can set minimum instances to 1,
which consumes the free CPU allowance faster - leave it at 0 for the demo.

## Demo posture (important)
Deploy with DEMO=1 for the link you share: the service is public and opens
straight into the demo workspace (synthetic data only). Do not put real
customer data behind a DEMO deployment - the secured mode (default) exists
for that, with a bootstrap key and per-tenant API keys.
