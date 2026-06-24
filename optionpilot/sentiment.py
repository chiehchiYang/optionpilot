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

import numpy as np
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


# ----------------------------------------------------------------------------------------------
# Composite PERP regime (the crypto-perp analog of MSCI): blend several positioning/turbulence
# signals into one "how risky is it to ADD long inventory right now" percentile. Like the VIX
# read, this is a REGIME CONTEXT, not a trade signal — and any gate built on it must be proven by
# backtest. Inputs (use whatever is available; Binance only serves ~30d of long/short & OI):
#   - realized vol (rolling std of log returns)  -> trend/turbulence (grids bleed in trends)
#   - funding rate                               -> long crowding / carry cost (high = overheated)
#   - long/short account ratio                   -> crowd positioning (high = crowded long)
#   - VIX                                        -> equity fear (the right gauge for US-stock perps)
# Each is mapped to its LOOKAHEAD-FREE expanding percentile, then averaged row-wise over the
# inputs that exist at that bar. Higher composite = riskier to add longs.
# ----------------------------------------------------------------------------------------------


def expanding_pct_series(series: pd.Series) -> pd.Series:
    """Per-point expanding percentile rank (0-100): each value's rank within history up to and
    including it. Lookahead-free; the last point equals expanding_pct_rank over the full series."""
    s = series.dropna().sort_index()
    seen: list[float] = []
    out_idx, out_val = [], []
    for idx, v in s.items():
        v = float(v)
        bisect.insort(seen, v)
        out_idx.append(idx)
        out_val.append(100.0 * bisect.bisect_right(seen, v) / len(seen))
    return pd.Series(out_val, index=out_idx)


def _asof_onto(s: pd.Series, index) -> pd.Series:
    """Forward-fill a datetime-indexed series onto `index` as-of (each target gets the last value
    at or before it — no lookahead)."""
    s = s.sort_index()
    return s.reindex(s.index.union(index)).ffill().reindex(index)


def _vix_onto(vp: pd.Series, index) -> pd.Series:
    """Map a date-indexed percentile series onto datetime bars by as-of date (no lookahead)."""
    pairs = sorted((x if isinstance(x, date) else pd.Timestamp(x).date(), float(v))
                   for x, v in vp.items())
    ds = [d for d, _ in pairs]
    vs = [v for _, v in pairs]
    out = []
    for ts in index:
        d = ts.date() if hasattr(ts, "date") else ts
        pos = bisect.bisect_right(ds, d) - 1
        out.append(vs[pos] if pos >= 0 else np.nan)
    return pd.Series(out, index=index)


def _perp_components(klines: pd.DataFrame, funding=None, long_short=None, vix=None,
                     vol_window: int = 24) -> dict[str, pd.Series]:
    """Each available sub-signal as an expanding-percentile series aligned to the klines index."""
    idx = klines.index
    comps: dict[str, pd.Series] = {}
    close = klines["close"].astype(float)
    rv = np.log(close).diff().rolling(int(vol_window)).std()
    comps["vol"] = expanding_pct_series(rv).reindex(idx).ffill()
    if funding is not None and len(funding):
        comps["funding"] = _asof_onto(
            expanding_pct_series(funding.set_index("funding_time")["funding_rate"]), idx)
    if long_short is not None and len(long_short):
        comps["long_short"] = _asof_onto(
            expanding_pct_series(long_short.set_index("time")["long_short_ratio"]), idx)
    if vix is not None and len(vix):
        comps["vix"] = _vix_onto(expanding_pct_series(vix), idx)
    return comps


def perp_risk_series(klines: pd.DataFrame, funding=None, long_short=None, vix=None,
                     vol_window: int = 24) -> pd.Series:
    """Lookahead-free per-bar COMPOSITE risk percentile (0-100; higher = riskier to add longs),
    the row-wise mean of whatever sub-signals are available. Feed to grid_backtest as `regime`."""
    comps = _perp_components(klines, funding, long_short, vix, vol_window)
    return pd.concat(comps.values(), axis=1).mean(axis=1, skipna=True)


def perp_regime(klines: pd.DataFrame, funding=None, long_short=None, vix=None,
                vol_window: int = 24) -> dict:
    """Current composite perp-regime read: each sub-signal's latest percentile + the blended
    risk score + a coarse label. A regime context, not a buy/sell signal."""
    comps = _perp_components(klines, funding, long_short, vix, vol_window)
    composite = pd.concat(comps.values(), axis=1).mean(axis=1, skipna=True)

    def _last(s: pd.Series):
        s = s.dropna()
        return round(float(s.iloc[-1]), 1) if len(s) else None

    score = _last(composite)
    label = "unknown"
    if score is not None:
        label = "calm" if score < 33 else "normal" if score < 66 else "stressed"
    return {
        "composite_risk_pct": score,
        "regime": label,
        "components": {k: _last(v) for k, v in comps.items()},
        "inputs_used": sorted(comps.keys()),
        "note": ("複合永續情緒:把波動、funding、多空比、VIX 各自的 expanding 百分位平均成一個"
                 "「加碼多單的風險度」(越高越不該追多)。這是 regime 背景、需回測驗證,不是買賣訊號。"),
    }
