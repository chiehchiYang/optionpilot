"""Variance-risk-premium analysis: is a name's implied vol overpriced vs realized?

Answers "is this ticker sweet for premium selling?" faster than a backtest — it needs no
trades, just the chain + underlying. Implied vol is computed with our own Black-Scholes
solver (so it works even when the data source doesn't ship greeks/IV). Crucially it splits
realized vol into upside/downside: for a PUT seller the relevant risk is the DOWNSIDE, and a
name that rocketed up (high total vol but modest downside) can still be "safe" to sell — yet
often a poor trade vs simply owning it (hence buy_hold_return is reported too).
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from optionpilot.data.greeks import implied_volatility


def realized_vol(underlying: pd.Series, periods: int = 252) -> dict:
    u = underlying.sort_index()
    r = np.log(u / u.shift(1)).dropna()
    r = np.asarray(r, dtype=float)

    def annualized(x):
        return float(x.std() * np.sqrt(periods)) if x.size > 1 else 0.0

    return {
        "realized_vol": annualized(r),
        "upside_vol": annualized(r[r > 0]),
        "downside_vol": annualized(r[r < 0]),
        "up_days": int((r > 0).sum()),
        "down_days": int((r < 0).sum()),
    }


def _implied_vols(opt_df: pd.DataFrame, underlying: pd.Series, rate: float,
                  dte_lo: int = 20, dte_hi: int = 60, min_price: float = 0.05) -> list[float]:
    """Per-day near-ATM implied vol via our solver (median of these is the IV estimate)."""
    u = underlying.sort_index()
    spot_by_date = {(d if isinstance(d, date) else pd.Timestamp(d).date()): float(v)
                    for d, v in u.items()}
    ivs: list[float] = []
    for d, day in opt_df.groupby("date"):
        spot = spot_by_date.get(d)
        if not spot or spot <= 0:
            continue
        day = day.copy()
        day["dte"] = (pd.to_datetime(day["expiry"]) - pd.to_datetime(d)).dt.days
        c = day[day["dte"].between(dte_lo, dte_hi) & (day["close"] > min_price)
                & (day["volume"].fillna(0) > 0)]
        if c.empty:
            continue
        atm = c.iloc[(c["strike"] - spot).abs().argmin()]
        try:
            iv = implied_volatility(float(atm["close"]), spot, float(atm["strike"]),
                                    atm["dte"] / 365.0, rate,
                                    "call" if atm["kind"] == "C" else "put")
            if 0.02 < iv < 8.0:
                ivs.append(iv)
        except Exception:  # noqa: BLE001 - skip un-invertible quotes
            continue
    return ivs


def support_resistance(ohlc: pd.DataFrame, lookback: int = 120, swing_window: int = 5,
                       n_levels: int = 3) -> dict:
    """Algorithmic support/resistance from OHLC: swing lows/highs + classic pivot points.

    Deterministic (no discretionary calls): swing lows/highs are local extrema over a
    +/- swing_window window; pivots are the textbook floor-trader levels from the last ~month.
    ohlc must have High/Low/Close columns (yfinance format).
    """
    df = ohlc.tail(lookback)
    close, lows, highs = df["Close"], df["Low"], df["High"]
    cur = float(close.iloc[-1])
    lo, hi = lows.to_numpy(dtype=float), highs.to_numpy(dtype=float)

    sw_lo, sw_hi, w = [], [], swing_window
    for i in range(w, len(df) - w):
        if lo[i] == lo[i - w:i + w + 1].min():
            sw_lo.append(float(lo[i]))
        if hi[i] == hi[i - w:i + w + 1].max():
            sw_hi.append(float(hi[i]))

    # nearest first: supports are swing lows just below price; resistances swing highs above.
    supports = sorted({round(x, 2) for x in sw_lo if x < cur}, reverse=True)[:n_levels]
    resistances = sorted({round(x, 2) for x in sw_hi if x > cur})[:n_levels]

    p = df.tail(21)  # ~last month
    H, L, C = float(p["High"].max()), float(p["Low"].min()), float(p["Close"].iloc[-1])
    P = (H + L + C) / 3.0
    pivots = {"P": P, "S1": 2 * P - H, "S2": P - (H - L), "S3": L - 2 * (H - P),
              "R1": 2 * P - L, "R2": P + (H - L), "R3": H + 2 * (P - L)}
    return {
        "current_price": round(cur, 2),
        "lookback_days": int(len(df)),
        "nearest_support": supports[0] if supports else None,
        "nearest_resistance": resistances[0] if resistances else None,
        "support_levels": supports,         # swing lows BELOW price, nearest -> furthest
        "resistance_levels": resistances,   # swing highs ABOVE price, nearest -> furthest
        "recent_low": round(float(lows.min()), 2),
        "recent_high": round(float(highs.max()), 2),
        "pivots": {k: round(v, 2) for k, v in pivots.items()},
        "note": ("support_levels are recent swing lows below the current price, ordered "
                 "nearest-to-furthest (not by time); resistance_levels are swing highs above, "
                 "nearest-to-furthest. pivots are classic floor-trader levels (P, S1-S3, "
                 "R1-R3). All are algorithmic levels from price history, not forecasts."),
    }


def implied_vol_timeseries(opt_df: pd.DataFrame, underlying: pd.Series, rate: float = 0.05,
                           dte_lo: int = 20, dte_hi: int = 60, min_price: float = 0.05):
    """Daily near-ATM implied vol as (sorted dates, ivs) — for the IV-vs-realized chart."""
    u = underlying.sort_index()
    spot_by_date = {(d if isinstance(d, date) else pd.Timestamp(d).date()): float(v)
                    for d, v in u.items()}
    out = []
    for d, day in opt_df.groupby("date"):
        spot = spot_by_date.get(d)
        if not spot or spot <= 0:
            continue
        day = day.copy()
        day["dte"] = (pd.to_datetime(day["expiry"]) - pd.to_datetime(d)).dt.days
        c = day[day["dte"].between(dte_lo, dte_hi) & (day["close"] > min_price)
                & (day["volume"].fillna(0) > 0)]
        if c.empty:
            continue
        atm = c.iloc[(c["strike"] - spot).abs().argmin()]
        try:
            iv = implied_volatility(float(atm["close"]), spot, float(atm["strike"]),
                                    atm["dte"] / 365.0, rate,
                                    "call" if atm["kind"] == "C" else "put")
            if 0.02 < iv < 8.0:
                out.append((d, iv))
        except Exception:  # noqa: BLE001
            continue
    out.sort(key=lambda x: x[0])
    return [d for d, _ in out], [iv for _, iv in out]


def measure_vrp(opt_df: pd.DataFrame, underlying: pd.Series, rate: float = 0.05) -> dict:
    """Implied vs realized vol (total + downside) + the variance risk premium + buy&hold."""
    rv = realized_vol(underlying)
    ivs = _implied_vols(opt_df, underlying, rate)
    iv = float(np.median(ivs)) if ivs else None
    u = underlying.sort_index()
    bh = float(u.iloc[-1] / u.iloc[0] - 1.0) if len(u) > 1 else 0.0

    out = {**rv, "implied_vol": iv, "iv_sample_days": len(ivs), "buy_hold_return": bh}
    if iv is not None:
        out["vrp_total"] = iv - rv["realized_vol"]
        out["vrp_downside"] = iv - rv["downside_vol"]   # the put-seller-relevant gap
    return out
