"""Tests for VIX sentiment: regime read, lookahead-free percentile, and the CSP regime gate."""

from datetime import date, timedelta

import pandas as pd

from optionpilot.backtest.strategies import CSPParams, cash_secured_put_backtest
from optionpilot.sentiment import expanding_pct_rank, vix_regime


def test_expanding_pct_rank_no_lookahead():
    idx = [date(2024, 1, 1) + timedelta(days=k) for k in range(5)]
    s = pd.Series([50.0, 40.0, 30.0, 20.0, 10.0], index=idx)   # strictly decreasing
    assert expanding_pct_rank(s, idx[0]) == 100.0               # first value is its own max
    assert expanding_pct_rank(s, idx[4]) == 20.0               # 1 of 5 history values <= 10
    assert expanding_pct_rank(s, idx[0] - timedelta(days=1)) is None  # nothing on/before -> None


def test_vix_regime_labels_and_percentile():
    idx = [date(2024, 1, 1) + timedelta(days=k) for k in range(10)]
    calm = vix_regime(pd.Series([12.0] * 10, index=idx))
    assert calm["regime"] == "calm" and calm["vix"] == 12.0
    stressed = vix_regime(pd.Series([float(v) for v in range(10, 60, 5)], index=idx))
    assert stressed["regime"] == "stressed"          # last value 55 > 30
    assert stressed["vix_percentile"] == 100.0        # 55 is the high of its own window


def _flat_chain(n_days=120, strike=95.0):
    start = date(2024, 1, 1)
    dates = [start + timedelta(days=k) for k in range(n_days)]
    rows = [{"date": d, "expiry": d + timedelta(days=30), "strike": strike, "kind": "P",
             "close": 1.0, "volume": 100, "bid": 1.0} for d in dates]
    under = pd.Series([100.0] * n_days, index=dates)             # flat -> puts expire OTM
    vix = pd.Series([float(n_days - k) for k in range(n_days)], index=dates)  # decreasing
    return pd.DataFrame(rows), under, vix


def test_regime_gate_is_a_pure_subset_of_baseline():
    opt, under, vix = _flat_chain()
    p = dict(entry_every_days=7, min_premium=0.01)
    base = cash_secured_put_backtest(opt, under, CSPParams(**p)).metrics
    n_base = base["n_trades"]
    assert n_base > 0

    # pct_min=0 lets everything through -> identical to baseline
    all_pass = cash_secured_put_backtest(
        opt, under, CSPParams(**p, vix_pct_min=0.0), vix=vix).metrics
    assert all_pass["n_trades"] == n_base

    # impossible band -> zero trades
    none_pass = cash_secured_put_backtest(
        opt, under, CSPParams(**p, vix_pct_min=101.0), vix=vix).metrics
    assert none_pass.get("n_trades", 0) == 0

    # a real threshold filters to a strict, non-empty subset (VIX high only early)
    filt = cash_secured_put_backtest(
        opt, under, CSPParams(**p, vix_pct_min=50.0), vix=vix).metrics
    assert 0 < filt["n_trades"] < n_base


def test_gate_inactive_without_vix_series():
    opt, under, _ = _flat_chain()
    # thresholds set but no vix passed -> gate must stay off (no accidental filtering)
    p = CSPParams(entry_every_days=7, min_premium=0.01, vix_pct_min=99.0)
    assert cash_secured_put_backtest(opt, under, p).metrics["n_trades"] > 0
