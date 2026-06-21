"""Test the walk-forward parameter sweep (train/test split + best-param selection)."""

from datetime import date, timedelta

import pandas as pd

from optionpilot.backtest.walkforward import walk_forward_csp


def _synthetic():
    """120 daily entries; puts at 90/93/95/97 strikes, 30-DTE, richer premium nearer the money.
    Flat underlying at 100 -> all puts expire OTM (keep premium)."""
    rows, u = [], {}
    d0 = date(2024, 1, 1)
    premium = {90.0: 0.5, 93.0: 1.0, 95.0: 1.5, 97.0: 2.0}
    for k in range(120):
        entry = d0 + timedelta(days=k)
        for strike, prem in premium.items():
            rows.append({"date": entry, "contract": f"{strike}-{k}",
                         "expiry": entry + timedelta(days=30), "strike": strike,
                         "kind": "P", "close": prem, "volume": 100})
    cur, last = d0, d0 + timedelta(days=155)
    while cur <= last:
        u[cur] = 100.0
        cur += timedelta(days=1)
    return pd.DataFrame(rows), pd.Series(u).sort_index()


def test_walk_forward_splits_and_picks_best():
    opt, under = _synthetic()
    res = walk_forward_csp(opt, under, split_frac=0.5, objective="total_return")
    assert "best_params" in res and "in_sample" in res and "out_of_sample" in res
    # both windows produced trades
    assert res["in_sample"]["n_trades"] > 0
    assert res["out_of_sample"]["n_trades"] > 0
    # only the 25-45 DTE window matches the 30-day options; richest premium = 0.97 moneyness
    assert res["best_params"]["dte_min"] == 25 and res["best_params"]["dte_max"] == 45
    assert res["best_params"]["target_moneyness"] == 0.97


def test_walk_forward_no_trades_returns_error():
    opt, under = _synthetic()
    # DTE window impossible for the 30-day options -> no in-sample trades
    res = walk_forward_csp(opt, under, grid=[{"dte_min": 100, "dte_max": 120}])
    assert "error" in res
