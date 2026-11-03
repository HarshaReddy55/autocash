# Deployment Guide

AutoCash product pack, document 5 of 8. Previous: Implementation Guide. Next: AWS Deployment Runbook.

## 5.1 Local Workstation Deployment

### Step 1: Build the Rust Native Kernel
```bash
cd rust-kernel
cargo build --release
cd ..
```
This compiles the kernel binary at `rust-kernel/target/release/autocash-kernel`; point the `AUTOCASH_KERNEL_BIN` environment variable at it. (The Docker build below compiles and places it automatically.)

### Step 2: Install Pinned Python Dependencies and Launch
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn api:app --app-dir backend/app --host 0.0.0.0 --port 8080
```
Navigate to `http://localhost:8080` to open the 14-page workspace.

## 5.2 Multi-Stage Docker Build
The root `Dockerfile` performs a reproducible two-stage build:
1. **Stage 1 (`rust:1.82-slim`):** Compiles `rust-kernel` in `--release` mode to produce the `autocash-kernel` binary.
2. **Stage 2 (`python:3.12-slim`):** Installs pinned dependencies from `backend/requirements.txt`, copies the compiled `autocash-kernel` binary, `backend/app`, `frontend`, and `docs`, runs as a non-root user (`autocash`), and starts `uvicorn` on port `8080`.

```bash
docker build -t autocash .
docker run -d -p 8080:8080 --name autocash autocash
```

## 5.3 Runtime Configuration Variables

| Environment Variable | Default | Purpose |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | Unset | Optional Google Gemini API key for live LLM remittance parsing and briefing generation. Falls back cleanly to deterministic parsing when unset or rate-limited. |
| `AUTOCASH_DATA_DIR` | `backend/data` | Filesystem path for the per-tenant and per-session SQLite `WAL` databases. The ECS deployment sets `/tmp/autocash-data`. |
| `GEMINI_MODEL` | code default | The Gemini model for live parsing. The production ECS environment sets `gemini-3.5-flash-lite` (the code-default thinking model exceeded the platform ingress time limit). |
| `AUTOCASH_KERNEL_BIN` | Unset | Path to the compiled Rust kernel binary; unset means the MILP decides every payment. |
| `AUTOCASH_RATE_LIMIT_PER_MIN` | `300` | Per-API-key request ceiling, per minute. |
| `AUTOCASH_BOOTSTRAP_KEY` | Unset (Open Demo Mode) | Optional master key to enforce API key authentication on administrative routes. |
| `AUTOCASH_SMTP_HOST`, `AUTOCASH_SMTP_USER`, `AUTOCASH_SMTP_PASSWORD`, `AUTOCASH_MAIL_FROM` | Unset | Optional SMTP configuration for live email dispatch. Until set, sends record as `recorded_not_sent`. The password is automatically redacted in `/api/v1/diagnostics`. |

---

Version 3.0 | 3 Nov 2026 | Owner: C. Harsha Vardhana Reddy
