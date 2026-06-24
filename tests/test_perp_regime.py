"""Tests for the composite perp-regime (PSCI) signal and its grid gate."""

import numpy as np
import pandas as pd

from optionpilot.backtest.grid import GridParams, grid_backtest
from optionpilot.sentiment import (
    expanding_pct_rank,
    expanding_pct_series,
    perp_regime,
    perp_risk_series,
)


def _klines(n=80, seed=0):
    idx = pd.date_range("2026-01-01", periods=n, freq="1h", tz="UTC")
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    return pd.DataFrame({"close": close}, index=idx)


def test_expanding_pct_series_matches_pointwise_and_monotone():
    dates = [d.date() for d in pd.date_range("2026-01-01", periods=10)]
    s = pd.Series([5, 3, 8, 1, 9, 2, 7, 4, 6, 0], index=dates)
    es = expanding_pct_series(s)
    assert abs(es.iloc[-1] - expanding_pct_rank(s, s.index[-1])) < 1e-9
    inc = pd.Series([1, 2, 3, 4, 5], index=[d.date() for d in pd.date_range("2026-02-01", periods=5)])
    assert (expanding_pct_series(inc) == 100.0).all()   # each new high -> 100th percentile


def test_perp_risk_series_vol_only_is_bounded():
    r = perp_risk_series(_klines())
    assert len(r) == 80
    assert r.dropna().between(0, 100).all()


def test_perp_risk_series_is_lookahead_free():
    kl = _klines(80)
    full = perp_risk_series(kl)
    half = perp_risk_series(kl.iloc[:40])
    # the first 40 bars must not depend on the later 40 (expanding/rolling look back only)
    assert np.allclose(full.iloc[:40].to_numpy(), half.to_numpy(), equal_nan=True)


def test_perp_risk_series_blends_available_inputs():
    kl = _klines(80)
    ft = kl.index[::8]
    funding = pd.DataFrame({"funding_time": ft, "funding_rate": np.linspace(0.0, 0.001, len(ft))})
    ls = pd.DataFrame({"time": kl.index, "long_short_ratio": np.linspace(1.0, 2.0, len(kl))})
    vix = pd.Series([15.0 + i * 0.1 for i in range(30)],
                    index=[d.date() for d in pd.date_range("2025-12-25", periods=30)])
    blended = perp_risk_series(kl, funding=funding, long_short=ls, vix=vix)
    assert len(blended) == 80 and blended.dropna().between(0, 100).all()


def test_perp_regime_snapshot_shape():
    out = perp_regime(_klines())
    assert out["regime"] in {"calm", "normal", "stressed", "unknown"}
    assert "vol" in out["components"] and "vol" in out["inputs_used"]
    assert out["composite_risk_pct"] is None or 0 <= out["composite_risk_pct"] <= 100


def _osc_klines():
    closes = [100, 99, 98, 99, 98, 97, 98, 97, 99, 98]
    idx = pd.date_range("2026-01-01", periods=len(closes), freq="1h", tz="UTC")
    return pd.DataFrame({"close": closes}, index=idx)


def test_grid_composite_gate_blocks_adds_when_risk_high():
    kl = _osc_klines()
    base = grid_backtest(kl, GridParams(lower=95, upper=102, n_grids=8))
    assert base["n_buys"] > 0   # oscillating-down: buys would fire without a gate

    high = pd.Series([100.0] * len(kl), index=kl.index)   # always "risky"
    blocked = grid_backtest(kl, GridParams(lower=95, upper=102, n_grids=8, regime_pct_max=50.0),
                            regime=high)
    assert blocked["composite_gated"] is True
    assert blocked["n_buys"] == 0 and blocked["buys_skipped_by_composite"] > 0

    low = pd.Series([10.0] * len(kl), index=kl.index)     # always "calm"
    allow = grid_backtest(kl, GridParams(lower=95, upper=102, n_grids=8, regime_pct_max=50.0),
                          regime=low)
    assert allow["n_buys"] == base["n_buys"] and allow["buys_skipped_by_composite"] == 0
