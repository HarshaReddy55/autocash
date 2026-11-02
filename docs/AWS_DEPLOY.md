# AutoCash - AWS Deployment Runbook (ECS Express Mode)
AutoCash product pack, document 6 of 8. Previous: Deployment Guide.
Next: Go-To-Market Plan.
Target: an always-on demonstration on Amazon ECS Express Mode
(Fargate), region ap-south-1 (Mumbai). Express Mode provisions the
service, a load balancer, HTTPS and an AWS URL (an ecs.ap-south-1.on.aws
address) from one container image. There is no additional charge for
Express Mode itself; the cost is the Fargate task and the load
balancer, about USD 28 per month at the sizes below, covered here by
account credits (USD 120 confirmed 31 Oct 2026).

Sizing: 0.25 vCPU, 1 GB memory. The measured application footprint is
about 153 MB of RAM; the 1 GB task size leaves headroom for the ML
stack on a throttled CPU. Autoscaling is capped at 3 tasks as a credit
guard.

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
workflow runs the full test suite first (133 tests plus the Rust
kernel tests); only a green suite builds and pushes the autocash:latest
image to ECR. The first build takes roughly ten minutes (the Rust
stage). Confirm the image: ECR, autocash, Images shows "latest".

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
- GET /health reports the demo-open posture, the model metrics and a
  clean AI error state.
- The homepage's asset URLs carry the current version stamp.
- Load the demo case, execute the run, and confirm the canonical
  outcome (10 auto-posted, 5 held for a person, 1 duplicate stopped).
- Submit a remittance to the parse endpoint and confirm the response
  is sourced from Gemini and passes the deterministic verifier.
- Open the diagnostics view: the Rust kernel probe agrees on all
  probed cases.

## Shipping an update
Commit and push through GitHub Desktop, wait for a green Actions run,
then one Update service action on the ECS service. Because the data
directory is ephemeral, expect tenant and workspace data to reset on
the update; reload the demo case afterwards. Verify the new asset
version stamp on the served page before declaring the update live.
The general update discipline is in the Deployment Guide (document 5).

## Notes and risks
- The filesystem is ephemeral: data resets if the task is replaced.
  Accepted for the demonstration; persistent storage is the
  paid-pilot step.
- Credit burn is roughly USD 28 per month while the service runs.
  Delete the Express service when the demonstration is no longer
  needed, to stop the burn.
- App Runner is closed to new customers (AWS notice); Express Mode is
  the recommended replacement and is available in all regions.
