"""Multi-dimensional stock screener / scorecard (technical + sentiment + fundamental + valuation).

This is a HYPOTHESIS-GENERATING screen, NOT a buy/sell signal and NOT a validated alpha. Two
deliberate design choices keep it honest (and unlike the black-box weighted indices we critique):
  1. Scores are CROSS-SECTIONAL PERCENTILE RANKS within the basket you pass — a name only looks
     "cheap" or "strong" relative to its peers, never on a magic absolute threshold.
  2. Dimensions are EQUAL-WEIGHTED and every sub-metric is shown raw, so nothing is hidden in a
     fitted weight. There is no optimisation here to overfit.
Anything this surfaces must then be run through the real backtest tools before you believe it.

Inputs we can actually get (free, via yfinance): price/volume for technical & a price-action
sentiment proxy (we have no news-NLP or dark-pool flow), and .info for fundamentals & valuation.
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd

# metric name -> (dimension, direction): +1 = higher raw is "better", -1 = lower is better.
_METRICS: list[tuple[str, str, int]] = [
    ("ret_3m", "technical", +1),
    ("dist_52w_high", "technical", +1),
    ("above_ma50", "technical", +1),
    ("above_ma200", "technical", +1),
    ("rsi14", "sentiment", +1),
    ("ret_1m", "sentiment", +1),
    ("rel_volume", "sentiment", +1),
    ("revenue_growth", "fundamental", +1),
    ("earnings_growth", "fundamental", +1),
    ("profit_margin", "fundamental", +1),
    ("roe", "fundamental", +1),
    ("debt_to_equity", "fundamental", -1),
    ("trailing_pe", "valuation", -1),
    ("forward_pe", "valuation", -1),
    ("price_to_sales", "valuation", -1),
    ("peg", "valuation", -1),
    ("ev_ebitda", "valuation", -1),
]
_DIMENSIONS = ["technical", "sentiment", "fundamental", "valuation"]
# "hotness" = trending/active right now (for the scanner's default ranking)
_HOTNESS = ["rel_volume", "abs_ret_1m", "realized_vol"]


def _rsi(close: pd.Series, n: int = 14) -> float | None:
    if len(close) <= n:
        return None
    d = close.diff()
    up = d.clip(lower=0).rolling(n).mean()
    down = (-d.clip(upper=0)).rolling(n).mean()
    rs = up / down.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    v = rsi.iloc[-1]
    return float(v) if v == v else None


def technical_metrics(ohlcv: pd.DataFrame) -> dict:
    """Price/volume metrics for the technical + (price-action) sentiment + hotness dimensions."""
    c = ohlcv["close"].astype(float)
    v = ohlcv["volume"].astype(float)

    def ret(n: int):
        return float(c.iloc[-1] / c.iloc[-1 - n] - 1) if len(c) > n else None

    out: dict = {"ret_1m": ret(21), "ret_3m": ret(63)}
    out["dist_52w_high"] = float(c.iloc[-1] / c.tail(252).max() - 1) if len(c) else None
    out["above_ma50"] = float(c.iloc[-1] / c.tail(50).mean() - 1) if len(c) >= 50 else None
    out["above_ma200"] = float(c.iloc[-1] / c.tail(200).mean() - 1) if len(c) >= 200 else None
    out["rsi14"] = _rsi(c, 14)
    out["rel_volume"] = (float(v.tail(5).mean() / v.tail(60).mean())
                         if len(v) >= 60 and v.tail(60).mean() else None)
    lr = np.log(c).diff().dropna()
    out["realized_vol"] = float(lr.tail(21).std() * np.sqrt(252)) if len(lr) >= 21 else None
    out["abs_ret_1m"] = abs(out["ret_1m"]) if out["ret_1m"] is not None else None
    return out


def metrics_for(ohlcv: pd.DataFrame | None, fundamentals: dict | None) -> dict:
    """Flat dict of every raw metric for one ticker (missing inputs -> the metric is absent)."""
    out: dict = {}
    if ohlcv is not None and not ohlcv.empty:
        out.update(technical_metrics(ohlcv))
    if fundamentals:
        for name in ("revenue_growth", "earnings_growth", "profit_margin", "roe",
                     "debt_to_equity", "trailing_pe", "forward_pe", "price_to_sales",
                     "peg", "ev_ebitda"):
            if fundamentals.get(name) is not None:
                out[name] = float(fundamentals[name])
    return out


def score_universe(rows: dict[str, dict]) -> dict[str, dict]:
    """Cross-sectional scorecard for a basket. rows: {ticker -> raw metrics from metrics_for}.

    Each metric is percentile-ranked ACROSS tickers (direction-adjusted), dimensions are the mean
    of their available metric scores, the composite is the equal-weighted mean of available
    dimensions, and `hotness` ranks how active/trending each name is. A metric ranked over <2
    valid tickers is dropped (you can't rank a single value) — so pass a basket, not one name."""
    df = pd.DataFrame(rows).T
    metric_dim = {n: d for n, d, _ in _METRICS}

    metric_score: dict[str, pd.Series] = {}
    for name, _dim, direction in _METRICS:
        if name not in df:
            continue
        col = pd.to_numeric(df[name], errors="coerce").dropna()
        if len(col) < 2:
            continue
        pct = col.rank(pct=True) * 100.0
        metric_score[name] = (100.0 - pct) if direction < 0 else pct

    hot_cols = []
    for name in _HOTNESS:
        if name in df:
            col = pd.to_numeric(df[name], errors="coerce").dropna()
            if len(col) >= 2:
                hot_cols.append(col.rank(pct=True) * 100.0)
    hotness = pd.concat(hot_cols, axis=1).mean(axis=1) if hot_cols else None

    out: dict[str, dict] = {}
    for t in df.index:
        per_dim: dict[str, list] = defaultdict(list)
        for name, s in metric_score.items():
            if t in s.index:
                per_dim[metric_dim[name]].append(float(s[t]))
        dims = {d: round(float(np.mean(per_dim[d])), 1) for d in _DIMENSIONS if per_dim[d]}
        comp = round(float(np.mean(list(dims.values()))), 1) if dims else None
        out[t] = {
            "composite": comp,
            "dimensions": dims,
            "hotness": (round(float(hotness[t]), 1)
                        if hotness is not None and t in hotness.index else None),
            "raw": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in rows[t].items()},
        }
    return out
