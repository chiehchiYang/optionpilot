"""Concrete option-selling strategy backtests on historical option-chain bars.

First strategy: systematic cash-secured put writing. On each cycle, sell one OTM put with
~target moneyness and DTE in a window, hold to expiry, and realize P&L against the underlying
at expiry. Costs (commission + a slippage haircut on premium) are modeled explicitly — for a
low-priced name like NOK these costs are large relative to premium, which is exactly the honest
lesson this engine exists to surface.

Data resolution is daily OHLCV per contract; we use each contract's `close` as its mark. This
is a first, deliberately simple cut (no intra-cycle management / rolling); option-quote-level
P&L is a later refinement.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from optionpilot.backtest.metrics import max_drawdown, sharpe_ratio, win_rate


@dataclass
class CSPParams:
    target_moneyness: float = 0.95          # sell strike ~ 95% of spot (OTM put)
    dte_min: int = 25
    dte_max: int = 45
    commission_per_contract: float = 0.65   # per leg, per contract (entry + assignment)
    slippage_frac: float = 0.05             # haircut on premium received (bid-ask/slippage)
    min_premium: float = 0.01               # ignore untradeable near-zero quotes
    min_contract_volume: int = 0            # require >= this day's volume to count as fillable
    risk_free_rate: float = 0.0             # annual rate earned on cash collateral (Step 2)
    cycles_per_year: float = 12.0           # for annualizing the (roughly monthly) cycles


@dataclass
class CSPResult:
    trades: list[dict] = field(default_factory=list)
    returns: np.ndarray = field(default_factory=lambda: np.array([]))
    metrics: dict = field(default_factory=dict)


def _asof_price(dates: list, prices: list, d) -> float | None:
    """Last underlying price on or before date d (dates sorted ascending)."""
    pos = bisect.bisect_right(dates, d) - 1
    return float(prices[pos]) if pos >= 0 else None


def cash_secured_put_backtest(
    opt_df: pd.DataFrame,
    underlying: pd.Series,
    params: CSPParams | None = None,
) -> CSPResult:
    """Backtest systematic cash-secured put writing.

    opt_df: normalized option chain (see data.sources) with columns
        `date`, `expiry`, `strike`, `kind`, `close`.
    underlying: Series indexed by date -> underlying close price.
    """
    p = params or CSPParams()

    d = opt_df
    cols = ["date", "strike", "expiry", "close", "volume"]
    puts = d[(d["kind"] == "P") & d["close"].notna() & (d["close"] >= p.min_premium)]
    puts = puts[[c for c in cols if c in puts.columns]].dropna(
        subset=["date", "strike", "expiry", "close"])
    if "volume" not in puts.columns:
        puts = puts.assign(volume=np.nan)
    if puts.empty:
        return CSPResult()

    by_date: dict = {dt: g for dt, g in puts.groupby("date")}
    calendar = sorted(by_date.keys())

    u = underlying.sort_index()
    u_dates = [x if isinstance(x, date) else pd.Timestamp(x).date() for x in u.index]
    u_prices = [float(x) for x in u.values]

    trades: list[dict] = []
    liquidity_skips = 0
    i = 0
    while i < len(calendar):
        entry = calendar[i]
        spot = _asof_price(u_dates, u_prices, entry)
        if spot is None or spot <= 0:
            i += 1
            continue

        cands = by_date[entry]
        lo = (pd.Timestamp(entry) + pd.Timedelta(days=p.dte_min)).date()
        hi = (pd.Timestamp(entry) + pd.Timedelta(days=p.dte_max)).date()
        cands = cands[(cands["expiry"] >= lo) & (cands["expiry"] <= hi)
                      & (cands["strike"] <= spot)]  # OTM puts only
        if cands.empty:
            i += 1
            continue

        # liquidity filter: only count contracts you could plausibly fill that day
        if p.min_contract_volume > 0:
            liquid = cands[cands["volume"].fillna(0) >= p.min_contract_volume]
            if liquid.empty:
                liquidity_skips += 1
                i += 1
                continue
            cands = liquid

        target = spot * p.target_moneyness
        pick = cands.iloc[(cands["strike"] - target).abs().argmin()]
        strike, expiry = float(pick["strike"]), pick["expiry"]
        premium = float(pick["close"]) * (1.0 - p.slippage_frac)
        entry_volume = pick["volume"]

        s_exp = _asof_price(u_dates, u_prices, expiry)
        if s_exp is None:
            break  # no underlying data through expiry; stop
        intrinsic = max(strike - s_exp, 0.0)
        assigned = intrinsic > 0
        commissions = p.commission_per_contract * (2 if assigned else 1)
        collateral = strike * 100.0
        days_held = max((expiry - entry).days, 0)
        interest = collateral * p.risk_free_rate * days_held / 365.0
        pnl = (premium - intrinsic) * 100.0 - commissions + interest
        ret = pnl / collateral

        trades.append({
            "entry": entry, "expiry": expiry, "spot": round(spot, 2), "strike": strike,
            "premium": round(premium, 4), "underlying_at_expiry": round(s_exp, 2),
            "assigned": assigned, "entry_volume": (None if pd.isna(entry_volume) else int(entry_volume)),
            "pnl": round(pnl, 2), "return": ret,
        })

        # next cycle: first trading day strictly after expiry
        i = bisect.bisect_right(calendar, expiry)

    returns = np.array([t["return"] for t in trades], dtype=float)
    metrics = {}
    if returns.size:
        total_return = float(np.prod(1.0 + returns) - 1.0)
        entry_vols = [t["entry_volume"] for t in trades if t["entry_volume"] is not None]
        metrics = {
            "n_trades": int(returns.size),
            "win_rate": win_rate(returns),
            "assigned_rate": float(np.mean([t["assigned"] for t in trades])),
            "mean_cycle_return": float(returns.mean()),
            "total_return": total_return,
            "sharpe_annualized": sharpe_ratio(returns, periods=p.cycles_per_year),
            "max_drawdown": max_drawdown(returns),
            "worst_trade": float(returns.min()),
            "liquidity_skips": liquidity_skips,
            "median_entry_volume": (float(np.median(entry_vols)) if entry_vols else None),
        }
        # Benchmark: buying & holding the underlying over the same traded window. Selling
        # premium can post a fine win-rate yet badly trail buy-and-hold (it caps upside) —
        # so this comparison is reported alongside, never omitted.
        s0 = _asof_price(u_dates, u_prices, trades[0]["entry"])
        s1 = _asof_price(u_dates, u_prices, trades[-1]["expiry"])
        if s0 and s1 and s0 > 0:
            bh = s1 / s0 - 1.0
            metrics["benchmark_buy_hold"] = bh
            metrics["excess_vs_buy_hold"] = total_return - bh
    return CSPResult(trades=trades, returns=returns, metrics=metrics)
