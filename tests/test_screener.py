"""Tests for the multi-dimensional screener engine (pure logic, no network)."""

import numpy as np
import pandas as pd

from optionpilot.screener import metrics_for, score_universe, technical_metrics


def _ohlcv(path, n=260, vol=1_000_000.0):
    idx = [d.date() for d in pd.date_range("2025-01-01", periods=n)]
    close = pd.Series(np.linspace(path[0], path[1], n), index=idx)
    return pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99,
                         "close": close, "volume": pd.Series([vol] * n, index=idx)})


_STRONG_F = {"trailing_pe": 40, "forward_pe": 35, "price_to_sales": 12, "peg": 2.5,
             "ev_ebitda": 30, "revenue_growth": 0.30, "earnings_growth": 0.40,
             "profit_margin": 0.25, "roe": 0.40, "debt_to_equity": 50}
_CHEAP_F = {"trailing_pe": 8, "forward_pe": 7, "price_to_sales": 1.5, "peg": 0.8,
            "ev_ebitda": 6, "revenue_growth": 0.05, "earnings_growth": 0.03,
            "profit_margin": 0.08, "roe": 0.10, "debt_to_equity": 120}
_MID_F = {"trailing_pe": 20, "forward_pe": 18, "price_to_sales": 5, "peg": 1.5,
          "ev_ebitda": 15, "revenue_growth": 0.15, "earnings_growth": 0.18,
          "profit_margin": 0.15, "roe": 0.22, "debt_to_equity": 80}


def test_technical_metrics_shape():
    m = technical_metrics(_ohlcv((100, 160)))
    for k in ("ret_1m", "ret_3m", "dist_52w_high", "above_ma50", "above_ma200", "rsi14",
              "rel_volume", "realized_vol"):
        assert k in m
    assert m["ret_3m"] > 0 and m["above_ma200"] > 0   # uptrend


def test_metrics_for_without_fundamentals_is_technical_only():
    m = metrics_for(_ohlcv((100, 110)), None)
    assert "ret_1m" in m and "trailing_pe" not in m


def _universe():
    return {
        "STRONG": metrics_for(_ohlcv((100, 170)), _STRONG_F),   # strong uptrend, expensive
        "MID": metrics_for(_ohlcv((100, 112)), _MID_F),
        "CHEAP": metrics_for(_ohlcv((120, 100)), _CHEAP_F),     # downtrend, cheap
    }


def test_score_universe_dimensions_and_bounds():
    scored = score_universe(_universe())
    for sc in scored.values():
        assert set(sc["dimensions"]) == {"technical", "sentiment", "fundamental", "valuation"}
        assert 0 <= sc["composite"] <= 100
        assert sc["hotness"] is None or 0 <= sc["hotness"] <= 100
        # composite is the equal-weighted mean of the available dimensions
        dims = list(sc["dimensions"].values())
        assert abs(sc["composite"] - sum(dims) / len(dims)) < 0.1


def test_uptrend_scores_higher_technical_than_downtrend():
    scored = score_universe(_universe())
    assert scored["STRONG"]["dimensions"]["technical"] > scored["CHEAP"]["dimensions"]["technical"]


def test_cheaper_name_scores_higher_valuation():
    scored = score_universe(_universe())
    assert scored["CHEAP"]["dimensions"]["valuation"] > scored["STRONG"]["dimensions"]["valuation"]


def test_better_fundamentals_score_higher():
    scored = score_universe(_universe())
    assert scored["STRONG"]["dimensions"]["fundamental"] > scored["CHEAP"]["dimensions"]["fundamental"]


def test_single_name_has_no_cross_sectional_score():
    # a metric ranked over <2 names is dropped -> no dimensions/composite for a lone ticker
    scored = score_universe({"AAPL": metrics_for(_ohlcv((100, 130)), _STRONG_F)})
    assert scored["AAPL"]["dimensions"] == {} and scored["AAPL"]["composite"] is None
