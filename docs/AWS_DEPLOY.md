# AWS Deployment Runbook

AutoCash product pack, document 6 of 8. Previous: Deployment Guide. Next: Go-To-Market Plan.

## 6.1 Production Environment Specification
AutoCash is deployed on **Amazon ECS Express Mode (ap-south-1, Mumbai)** using **Amazon ECR** for container registry storage, behind the Express Mode HTTPS endpoint.

* **Live Endpoint:** `https://au-060cf7bb8b42492097645654b34ab8d6.ecs.ap-south-1.on.aws/`
* **AWS Region:** `ap-south-1`
* **Container Port:** `8080`
* **ALB Health Check:** `GET /health` (expects HTTP `200 OK`)
* **Task Resources:** 0.25 vCPU, 1 GB memory, non-root container execution. Autoscaling is capped at 3 tasks as a credit guard on the account's $120 of credits; the service burns roughly $28 per month.

## 6.2 Deploying a New Release
Production releases do not use a local script: the path is GitHub Actions plus one action in the ECS console.

1. Copy the changed files into the repository and commit (GitHub Desktop), then Push origin.
2. GitHub Actions runs the test job; on green, it builds the image and pushes it to ECR (section 6.3).
3. In the ECS console, open the `autocash` service (Express Mode, cluster `default`) and choose **Update service**. ECS rolls the new task in, verifies `/health`, and drains the previous task.
4. Run the post-deployment verification checklist (section 6.4). Note that workspace data lives in the task's `/tmp` and resets on redeploy; re-seed the demo case from Use Cases (one action).

A `deploy.sh` file exists in the repository root, but it is a legacy Google Cloud Run helper from an earlier hosting evaluation. It is not part of the production path and must not be used to deploy this service.

## 6.3 CI/CD Pipeline (`.github/workflows/build-ecr.yml`)
On every push to `main`, GitHub Actions:
1. Runs the full test gate in a dedicated test job: the `pytest` suite (134 tests across 29 modules) and the Rust kernel's `cargo test`.
2. Blocks image publication if any unit, accounting, or UI contract test fails (a red test job skips the build job entirely).
3. Builds and pushes the verified container image to Amazon ECR.

## 6.4 Post-Deployment Verification Checklist
1. **Health Probe:** Open `/health` and confirm HTTP 200 and `"status": "ok"`.
2. **Subsystem Diagnostics:** Open `11 Agent Health` in the UI (or `GET /api/v1/diagnostics`) and verify:
   * The Rust kernel equivalence probe passes against the Python reference.
   * The AI state reports Gemini configured with no last error (a live parse returns `source: gemini`).
   * SQLite `WAL` mode is active.
3. **End-to-End Smoke Test:** Load the Demo Case (`19` open invoices, `16` staged wires), verify the Staged Readiness Panel on `01 Dashboard`, click **Run Reconciliation**, and confirm `10` auto-posted matches (`411,800.00`), `5` held matches (`223,150.00`), and `1` exception.

---

Version 3.0 | 3 Nov 2026 | Owner: C. Harsha Vardhana Reddy
