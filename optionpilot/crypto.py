"""Analysis for USDⓈ-M perpetual futures — the funding-carry edge + realized vol.

These perps include US-stock underlyings (NOKUSDT, AAPLUSDT, TSLAUSDT, SPYUSDT…). For a
stock perp, the funding rate is the structural analog of the options variance-risk-premium:
it is what longs pay shorts each interval to hold leveraged exposure, and it embeds the cost
of carry (financing + borrow + any dividend adjustment). A persistently POSITIVE funding rate
means the crowd is paying to be long — so the structurally-favoured side is to be SHORT the
perp (delta-hedged with the underlying = a cash-and-carry basis trade) and harvest the funding.

Like VRP, a fat funding rate is not automatically free money: it can be compensation for real
move risk. We report it honestly (annualized, % of intervals positive, recent trend) so the
agent can weigh carry vs. the directional risk it is being paid for.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

HOURS_PER_YEAR = 24 * 365


def _infer_interval_hours(funding_time: pd.Series) -> float:
    """Median spacing between funding events, in hours (Binance is usually 8h = 3x/day)."""
    if len(funding_time) < 2:
        return 8.0
    gaps = funding_time.sort_values().diff().dropna().dt.total_seconds() / 3600.0
    g = float(np.median(gaps))
    return g if g > 0 else 8.0


def funding_summary(funding: pd.DataFrame, recent_n: int = 21) -> dict:
    """Summarize funding-rate history into a carry verdict.

    funding: DataFrame with funding_time + funding_rate (decimal per interval), as returned by
    data.binance.funding_rate_history. recent_n = how many latest intervals define "recent".
    """
    if funding is None or funding.empty:
        return {"n": 0, "note": "沒有 funding 資料"}

    f = funding.sort_values("funding_time")
    rate = f["funding_rate"].astype(float).to_numpy()
    interval_h = _infer_interval_hours(f["funding_time"])
    per_year = HOURS_PER_YEAR / interval_h

    mean_r = float(rate.mean())
    recent = rate[-recent_n:]
    recent_mean = float(recent.mean()) if recent.size else mean_r

    longs_pay = mean_r > 0
    annualized = mean_r * per_year
    return {
        "n": int(rate.size),
        "start": f["funding_time"].iloc[0].date().isoformat(),
        "end": f["funding_time"].iloc[-1].date().isoformat(),
        "interval_hours": round(interval_h, 2),
        "events_per_year": round(per_year, 1),
        "mean_rate": mean_r,                       # per-interval, decimal
        "median_rate": float(np.median(rate)),
        "last_rate": float(rate[-1]),
        "recent_mean_rate": recent_mean,           # mean of last recent_n intervals
        "annualized_funding": annualized,          # decimal, e.g. 0.11 = 11%/yr
        "annualized_funding_pct": round(annualized * 100, 2),
        "recent_annualized_pct": round(recent_mean * per_year * 100, 2),
        "pct_intervals_positive": round(float((rate > 0).mean()) * 100, 1),
        "direction": "longs_pay_shorts" if longs_pay else "shorts_pay_longs",
        "carry_side": "short_perp" if longs_pay else "long_perp",
        "note": (
            ("多方付錢給空方:結構上偏向「做空永續 + 用標的對沖」收 funding 的現金套利"
             if longs_pay else
             "空方付錢給多方:結構上偏向「做多永續」收 funding")
            + f";年化約 {round(annualized * 100, 2)}%。高 funding 不等於穩賺,"
              "它可能是在補償真實的方向風險(等同 VRP 的邏輯)。股票永續的 funding "
              "還內含融資成本與股息調整。"
        ),
    }


def realized_vol_from_klines(klines: pd.DataFrame, periods_per_year: int | None = None) -> dict:
    """Annualized realized vol from kline closes (total + upside/downside split).

    periods_per_year defaults to a guess from the median bar spacing (e.g. hourly -> 24*365).
    """
    if klines is None or klines.empty or "close" not in klines:
        return {"realized_vol": 0.0, "bars": 0}
    c = klines["close"].astype(float)
    r = np.log(c / c.shift(1)).dropna().to_numpy()
    if r.size < 2:
        return {"realized_vol": 0.0, "bars": int(r.size)}

    if periods_per_year is None:
        idx = klines.index
        if len(idx) > 1 and hasattr(idx, "to_series"):
            bar_h = float(np.median(idx.to_series().diff().dropna().dt.total_seconds()) / 3600.0)
            periods_per_year = int(HOURS_PER_YEAR / bar_h) if bar_h > 0 else 365
        else:
            periods_per_year = 365

    ann = np.sqrt(periods_per_year)
    return {
        "realized_vol": float(r.std() * ann),
        "upside_vol": float(r[r > 0].std() * ann) if (r > 0).sum() > 1 else 0.0,
        "downside_vol": float(r[r < 0].std() * ann) if (r < 0).sum() > 1 else 0.0,
        "bars": int(r.size),
        "periods_per_year": int(periods_per_year),
    }
