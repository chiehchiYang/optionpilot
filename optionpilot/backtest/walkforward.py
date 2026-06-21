"""Walk-forward parameter sweep for the cash-secured-put strategy.

"Tune to best" honestly: pick the best parameter set on an in-sample (train) window, then
evaluate ONLY that set on the out-of-sample (test) window. If out-of-sample is much worse than
in-sample, the tuning was overfit — the whole point of doing this rather than reporting the
best backtest over the full history.
"""

from __future__ import annotations

import pandas as pd

from optionpilot.backtest.strategies import CSPParams, cash_secured_put_backtest

# A small, sensible default grid: strike moneyness x DTE window.
DEFAULT_GRID = [
    {"target_moneyness": m, "dte_min": lo, "dte_max": hi}
    for m in (0.90, 0.93, 0.95, 0.97)
    for (lo, hi) in ((7, 21), (25, 45), (45, 75))
]


def _split_date(opt_df: pd.DataFrame, frac: float):
    dates = sorted(opt_df["date"].unique())
    return dates[min(int(len(dates) * frac), len(dates) - 1)]


def walk_forward_csp(
    opt_df: pd.DataFrame,
    underlying: pd.Series,
    grid: list[dict] | None = None,
    split_frac: float = 0.5,
    objective: str = "total_return",
    base: dict | None = None,
) -> dict:
    """Sweep `grid` on the train window, pick the best by `objective`, evaluate on test.

    The underlying is passed whole to both halves so trades entered near the split can still
    be priced at expiry; only the ENTRY window (option dates) is split.
    """
    grid = grid or DEFAULT_GRID
    base = base or {}
    split = _split_date(opt_df, split_frac)
    train_opt = opt_df[opt_df["date"] <= split]
    test_opt = opt_df[opt_df["date"] > split]

    results = []
    for combo in grid:
        m = cash_secured_put_backtest(train_opt, underlying, CSPParams(**{**base, **combo})).metrics
        score = m.get(objective) if m.get("n_trades", 0) > 0 else None
        results.append({"params": combo, "score": score, "train_metrics": m})

    scored = [r for r in results if r["score"] is not None]
    if not scored:
        return {"error": "no parameter set produced in-sample trades", "split_date": str(split)}

    best = max(scored, key=lambda r: r["score"])
    oos = cash_secured_put_backtest(
        test_opt, underlying, CSPParams(**{**base, **best["params"]})).metrics

    return {
        "split_date": str(split),
        "objective": objective,
        "best_params": best["params"],
        "in_sample": best["train_metrics"],
        "out_of_sample": oos,
        "grid_size": len(grid),
        "grid_scored": len(scored),
    }
