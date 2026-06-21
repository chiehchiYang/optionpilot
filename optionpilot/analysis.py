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
