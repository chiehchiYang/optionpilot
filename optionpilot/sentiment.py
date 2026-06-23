"""Market-sentiment / regime reads for the options desk.

Sentiment here is a REGIME CONTEXT, not a standalone buy/sell signal: it tells you which market
you are standing in so a strategy can be conditioned on it (and that conditioning then has to be
proven by backtest, like everything else). The equity fear gauge is the CBOE VIX; we read its
level, its percentile vs recent history, and a coarse regime label. We also expose a
LOOKAHEAD-FREE expanding percentile rank used to gate backtest entries by regime.
"""

from __future__ import annotations

import bisect
from datetime import date

import pandas as pd

# coarse VIX level bands (annualized vol points) -> regime label
_BANDS = [(15.0, "calm"), (20.0, "normal"), (30.0, "elevated"), (float("inf"), "stressed")]


def _label(vix_level: float) -> str:
    for hi, name in _BANDS:
        if vix_level < hi:
            return name
    return "stressed"


def expanding_pct_rank(series: pd.Series, asof) -> float | None:
    """Percentile rank (0-100) of the value at `asof` within history UP TO and INCLUDING asof.

    No lookahead: only data on/before `asof` is used — safe to call inside a backtest entry gate.
    """
    s = series.sort_index()
    dates = [x if isinstance(x, date) else pd.Timestamp(x).date() for x in s.index]
    vals = [float(v) for v in s.values]
    pos = bisect.bisect_right(dates, asof if isinstance(asof, date) else pd.Timestamp(asof).date()) - 1
    if pos < 0:
        return None
    cur = vals[pos]
    hist = vals[: pos + 1]
    return 100.0 * sum(1 for v in hist if v <= cur) / len(hist)


def vix_regime(vix: pd.Series, lookback: int = 252) -> dict:
    """Current VIX level + percentile over the last `lookback` sessions + a coarse regime label."""
    s = vix.sort_index().dropna()
    if s.empty:
        return {"note": "沒有 VIX 資料"}
    cur = float(s.iloc[-1])
    window = s.tail(lookback)
    pct = 100.0 * float((window <= cur).mean())
    return {
        "vix": round(cur, 2),
        "vix_percentile": round(pct, 1),         # vs last `lookback` sessions
        "regime": _label(cur),
        "lookback": int(min(lookback, len(s))),
        "mean": round(float(window.mean()), 2),
        "note": ("VIX 是股市恐懼計:越高代表越怕、選擇權權利金越肥(但風險也越大)。"
                 "百分位高=相對自身近期偏貴。這是 regime 背景,不是買賣訊號。"),
    }
