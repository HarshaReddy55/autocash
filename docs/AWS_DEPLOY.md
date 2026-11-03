# AutoCash - AWS Deployment Runbook (ECS Express Mode)
AutoCash product pack, document 6 of 8. Previous: Deployment Guide.
Next: Go-To-Market Plan.
This is the runbook for the live reference deployment, followed step
by step to produce the running service. The general deployment model
for any host is document 5 of this pack.

## 1. Production environment specification

| Item | Value |
| :--- | :--- |
| Cloud service | Amazon ECS, Express Mode (Fargate), which provisions the service, load balancer, HTTPS and a public URL from one container image |
| Region | ap-south-1 (Mumbai) |
| Cluster | default |
| Service name | autocash |
| Container registry | Amazon ECR, private repository: autocash |
| Image | Built by GitHub Actions from the repository Dockerfile on every push to main |
| Task sizing | 0.25 vCPU, 1 GB memory (the measured application footprint is about 153 MB of RAM; the size leaves headroom for the ML stack on a throttled CPU) |
| Autoscaling | Maximum 3 tasks, set deliberately as a credit guard |
| Container port | 8080 |
| Health check | /health on the service; the image's own healthcheck answers at /ready |
| Data | AUTOCASH_DATA_DIR=/tmp/autocash-data on the task: ephemeral by design, resets on redeploy (see section 4) |
| Cost | About USD 28 per month while the service runs, covered by account credits (USD 120 confirmed 31 Oct 2026); there is no additional charge for Express Mode itself |
| Public URL | The ecs.ap-south-1.on.aws address the console issues at creation |

## Step 1 - Code complete on GitHub
The repository (HarshaReddy55/autocash) must contain the full tree:
backend, frontend, docs, rust-kernel and the .github workflow. Push
through GitHub Desktop; the web uploader drops folders.

## Step 2 - Create the ECR repository
AWS Console (region Asia Pacific, Mumbai, ap-south-1), Elastic
Container Registry, Create repository: name "autocash", private, tag
mutability Mutable. Create.

## Step 3 - Create the deployer IAM user
IAM, Users, Create user: name "github-deployer", no console access.
Attach the policy AmazonEC2ContainerRegistryPowerUser. Then open the
user, Security credentials, Create access key, use case "Third-party
service". Keep the access key ID and secret access key on screen for
Step 4; they are entered into GitHub, never into chat or documents.

## Step 4 - GitHub secrets
Repository, Settings, Secrets and variables, Actions, New repository
secret:
- AWS_ACCESS_KEY_ID: the key from Step 3
- AWS_SECRET_ACCESS_KEY: the secret from Step 3
- AWS_ACCOUNT_ID: the 12-digit account ID (console, top right)

## Step 5 - Push and watch the build
Push to main from GitHub Desktop. In the repository's Actions tab, the
workflow (.github/workflows/build-ecr.yml) runs its test job first:
the full pytest suite (134 tests) plus the Rust kernel tests
(cargo test). The build job depends on the test job; only a green
suite builds and pushes the autocash:latest image to ECR. The first
build takes roughly ten minutes (the Rust stage). Confirm the image:
ECR, autocash, Images shows "latest".

A note from the run history: a red test job means no image is built
and the service keeps running the previous version. That gate is the
point of the pipeline, not an obstacle to route around.

## Step 6 - Create the Express Mode service
ECS Console, Create, Express Mode service:
- Name: autocash
- Container image: the ECR autocash:latest URI
- Container port: 8080
- CPU: 0.25 vCPU, Memory: 1 GB
- Health check path: /health
- Task execution role and infrastructure role: accept the defaults
  the console offers
- Autoscaling: maximum 3 tasks (credit guard)
- Environment variables:
  AUTOCASH_DATA_DIR=/tmp/autocash-data
  AUTOCASH_RATE_LIMIT_PER_MIN=300
  OMP_NUM_THREADS=1, OPENBLAS_NUM_THREADS=1, MKL_NUM_THREADS=1
  GEMINI_API_KEY=<the project's Gemini key> (enables AI parsing)
  GEMINI_MODEL=gemini-3.5-flash-lite
- Do NOT set AUTOCASH_BOOTSTRAP_KEY for the demonstration (demo-open
  posture, synthetic data only; set it later for secured mode).
Create. Within a few minutes the service shows its public URL.

Two environment lessons, learned the hard way and recorded so they are
not repeated. First, GEMINI_MODEL must be set explicitly: an earlier
deployment ran for days on a built-in default model because the
variable had never been added, and that default model answers so
slowly that requests died at the platform's sixty-second ceiling.
Second, the API key is currently stored as a plain environment
variable. The console offers a Secret type backed by Secrets Manager;
converting is a deliberate later cleanup, not a launch blocker, because
the key's exposure is limited to free-tier quota on a sole-access
account and Secrets Manager carries a small monthly fee against the
zero-cost rule.

## Step 7 - Verify the live service
Verification is done against the served product, not the console:
- GET /health reports status ok, the demo-open posture (auth:
  dev-open), the canonical model metrics (delay MAE 2.948 against the
  7.665 baseline, validity AUC 0.846), Gemini configured, and no AI
  error.
- The homepage's asset URLs carry the current version stamp.
- GET /api/v1/evaluations reports MILP accuracy 1.0 against greedy 0.8.
- Load the demo case, execute the run, and confirm the canonical
  outcome: 10 auto-posted ($411,800), 5 held for a person ($223,150),
  1 duplicate stopped before matching.
- Submit a remittance to the parse endpoint and confirm the response
  is sourced from Gemini (source=gemini, not degraded) and passes the
  deterministic verifier.
- Open the diagnostics view: the Rust kernel probe agrees on all
  probed cases, and the mail password is redacted.
- Approve the partial payment and confirm its SAP clearing document
  balances, with the residual receivable line present.

## 2. Shipping an update
1. Copy the changed files into the repository folder, commit through
   GitHub Desktop with a summary that names the version and the
   change, and Push origin.
2. Wait for the Actions run to go green (test job, then build job).
   A red run means no new image exists; do not touch the service.
3. On the ECS service, take the one Update service action so the
   service rolls to the new image.
4. Verify against the served product (Step 7), starting with the
   asset version stamp on the homepage: a changed stamp proves the
   new build is the one being served.
Because the data directory is ephemeral, expect tenant and workspace
data to reset on the update; reload the demo case afterwards (one
action from Use Cases). The general update discipline is in the
Deployment Guide (document 5).

## 3. What this runbook is not
A deploy.sh script exists in the repository root. It is not the
production path and was not used to deploy the live service; the flow
above (GitHub Actions build, ECR image, one Update service action) is
the entire release mechanism. Do not improvise a second one.

## 4. Notes and risks
- The filesystem is ephemeral: data resets if the task is replaced.
  Accepted for the demonstration; persistent storage is the
  paid-pilot step.
- Credit burn is roughly USD 28 per month while the service runs.
  Delete the Express service when the demonstration is no longer
  needed, to stop the burn.
- App Runner is closed to new customers (AWS notice); Express Mode is
  the recommended replacement and is available in all regions.

Version 3.0 | 3 Nov 2026 | Owner: C. Harsha Vardhana Reddy
