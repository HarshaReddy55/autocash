# AutoCash - Autonomous Cash Application Agent

AutoCash matches incoming payments to open invoices autonomously, explains
every decision, and routes only true exceptions to humans. Its design rule:
AI proposes, deterministic solvers dispose.

## Quick start
    python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
    .venv/bin/python -m uvicorn api:app --app-dir backend/app --port 8080
Open http://localhost:8080 for the product UI. Seed the demo workspace from
the dashboard, run a reconciliation batch, and inspect matches, exceptions,
forecasts and evaluations - all computed live by the API.

Docker: `docker build -t autocash .` then run with AUTOCASH_BOOTSTRAP_KEY set
(see docs/IMPLEMENTATION_GUIDE.md).

## What is inside
- backend/app - FastAPI service: MILP + greedy solvers, batch orchestration,
  CSV ingestion, deduction intelligence, ML models, forecast, AI parsing with
  verifier + fallback, grounded copilot, tenancy/auth/RBAC, observability.
- rust-kernel - Rust subset-sum matching kernel (cargo test: 4 passing) with
  a Python reference implementation and 203-case equivalence tests.
- frontend - product UI served by the API, wired to live endpoints.
- docs - ARCHITECTURE.md, PRD.md, IMPLEMENTATION_GUIDE.md, GO_TO_MARKET.md.

## Verification
    .venv/bin/python -m pytest backend/tests/ -q     # 19 tests
    cd rust-kernel && cargo test                     # 4 tests
All metrics quoted in docs are computed on labelled synthetic seed data and
say so; vendor benchmarks are market context, never this product's results.

## Configuration (environment)
AUTOCASH_DATA_DIR, AUTOCASH_BOOTSTRAP_KEY, AUTOCASH_RATE_LIMIT_PER_MIN,
GEMINI_API_KEY (optional; without it, parsing runs in deterministic mode).
