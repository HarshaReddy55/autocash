# AutoCash on AWS - ECS Express Mode runbook

Target: an always-on demo on Amazon ECS Express Mode (Fargate), region
ap-south-1 (Mumbai). Express Mode provisions the service, an Application
Load Balancer, HTTPS and an AWS URL (name.ecs.ap-south-1.on.aws) from one
container image. No additional charge for Express Mode itself; you pay for
the Fargate task and the ALB (about USD 28/month at the sizes below),
covered here by account credits (USD 120 confirmed 31 Oct 2026).

Sizing: 0.25 vCPU / 1 GB. Measured app footprint is ~153 MB RAM; the 1 GB
task size leaves headroom for the ML stack under the throttled CPU.

## Step 1 - Code complete on GitHub
Repo HarshaReddy55/autocash must contain the full tree (backend, frontend,
docs, rust-kernel folders plus .github). Push via GitHub Desktop (the web
uploader drops folders).

## Step 2 - Create the ECR repository
AWS Console (region Asia Pacific Mumbai, ap-south-1) > Elastic Container
Registry > Create repository: name "autocash", private, tag mutability
Mutable. Create.

## Step 3 - Create the deployer IAM user
IAM > Users > Create user: name "github-deployer" (no console access).
Attach policy: AmazonEC2ContainerRegistryPowerUser.
Then open the user > Security credentials > Create access key > use case
"Third-party service" > create. Keep the Access key ID and Secret access
key on screen for Step 4 (they are entered into GitHub, never into chat).

## Step 4 - GitHub secrets
Repo > Settings > Secrets and variables > Actions > New repository secret:
- AWS_ACCESS_KEY_ID = the key from Step 3
- AWS_SECRET_ACCESS_KEY = the secret from Step 3
- AWS_ACCOUNT_ID = your 12-digit AWS account ID (console, top right)

## Step 5 - Push and watch the build
Push to main (GitHub Desktop). Repo > Actions tab: the "Build and push
image to Amazon ECR" workflow builds the Dockerfile and pushes
autocash:latest to ECR. First build takes roughly 10 minutes (Rust stage).
Confirm the image exists: ECR > autocash > Images shows "latest".

## Step 6 - Create the Express Mode service
ECS Console > Create > Express Mode service (or Clusters > Create service
with the Express option):
- Name: autocash
- Container image: the ECR autocash:latest URI
- Container port: 8080
- CPU: 0.25 vCPU, Memory: 1 GB
- Health check path: /health
- Task execution role and infrastructure role: let the console create or
  select the defaults it offers
- Environment variables:
  AUTOCASH_DATA_DIR=/tmp/autocash-data
  AUTOCASH_RATE_LIMIT_PER_MIN=300
  OMP_NUM_THREADS=1, OPENBLAS_NUM_THREADS=1, MKL_NUM_THREADS=1
- Do NOT set AUTOCASH_BOOTSTRAP_KEY (demo posture: opens straight into
  the demo workspace; set it later for secured mode)
Create. In a few minutes the service shows a URL like
https://autocash.ecs.ap-south-1.on.aws - that is the demo link.

## Step 7 - Verify (Muse)
Hand the URL over; verification = /ready ready:true, homepage loads,
seed + batch run + forecast + copilot all exercised live.

## Notes and risks
- Filesystem is ephemeral (same as other demo hosts): tenant data resets
  if the task is replaced. Fine for the demo; persistent storage is the
  paid-pilot step (documented in docs/DEPLOY.md).
- Credit burn is roughly USD 28/month while the service runs. Delete the
  Express service when the demo is no longer needed to stop the burn.
- App Runner is closed to new customers (AWS notice); Express Mode is
  AWS's recommended replacement and is available in all regions.
