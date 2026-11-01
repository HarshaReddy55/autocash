"""Forecasting + collections prioritisation on top of the delay model.
Bands come from bootstrapping the model's holdout residuals: honest
uncertainty, not decorative percentages."""
import numpy as np
from ml import predict_delay

def forecast_cash_in(open_invoices, delay_model, horizon_days=30, residual_std=3.5, current_month=10, n_sims=400, seed=3):
    rng = np.random.default_rng(seed)
    weekly = {}
    detail = []
    for inv in open_invoices:
        delay = predict_delay(delay_model, inv.customer, 30, inv.gross_cents, current_month)
        expected_in = -inv.due_in_days + delay  # days from today until cash lands
        sims = expected_in + rng.normal(0, residual_std, n_sims)
        within = sims[(sims >= 0) & (sims <= horizon_days)]
        p_land = len(within) / n_sims
        detail.append({"invoice_id": inv.invoice_id, "customer": inv.customer,
                       "gross_cents": inv.gross_cents, "expected_in_days": round(float(expected_in), 1),
                       "prob_within_horizon": round(float(p_land), 3)})
        for s in within:
            wk = int(s // 7)
            weekly.setdefault(wk, []).append(inv.gross_cents)
    weeks = []
    for wk in sorted(weekly):
        vals = weekly[wk]
        # bootstrap band: resample invoice inclusion by landing probability mass per week
        totals = []
        for _ in range(200):
            idx = rng.integers(0, len(vals), len(vals))
            totals.append(sum(vals[i] for i in idx))
        totals = np.array(totals, dtype=float)
        weeks.append({"week": wk + 1, "p10_cents": int(np.percentile(totals, 10)),
                      "p50_cents": int(np.percentile(totals, 50)), "p90_cents": int(np.percentile(totals, 90))})
    return {"horizon_days": horizon_days, "weeks": weeks, "invoices": detail}

def prioritise_collections(open_invoices, delay_model, current_month=10):
    scored = []
    for inv in open_invoices:
        delay = predict_delay(delay_model, inv.customer, 30, inv.gross_cents, current_month)
        overdue = max(0, -inv.due_in_days)
        # expected value at risk: amount x lateness pressure; delay raises urgency
        score = (inv.gross_cents / 100.0) * (1 + overdue / 30.0) * (1 + max(delay, 0) / 20.0)
        scored.append({"invoice_id": inv.invoice_id, "customer": inv.customer,
                       "gross_cents": inv.gross_cents, "overdue_days": overdue,
                       "predicted_delay_days": round(float(delay), 1), "priority_score": round(float(score), 2)})
    return sorted(scored, key=lambda r: -r["priority_score"])
