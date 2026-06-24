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
    target_moneyness: float = 0.95          # put/call strike ~ this fraction of spot (OTM)
    call_moneyness: float = 1.05            # wheel's call leg: sell call ~ this multiple of spot
    dte_min: int = 25
    dte_max: int = 45
    commission_per_contract: float = 0.65   # per leg, per contract (entry + assignment)
    use_bid_ask: bool = True                # sell-to-open fills at the real bid when available
    slippage_frac: float = 0.05             # fallback haircut when no bid/ask (e.g. OHLCV source)
    min_premium: float = 0.01               # ignore untradeable near-zero quotes
    min_contract_volume: int = 0            # require >= this day's volume to count as fillable
    risk_free_rate: float = 0.0             # annual rate earned on cash collateral (Step 2)
    cycles_per_year: float = 12.0           # for annualizing; auto-set when entry_every_days>0
    # Optional VIX regime gate (sentiment filter). When a `vix` series is passed to the backtest,
    # only enter on a date whose VIX expanding-percentile (lookahead-free) is within this band.
    # None = no gate. e.g. vix_pct_min=50 -> only sell puts when fear is above its running median.
    vix_pct_min: float | None = None
    vix_pct_max: float | None = None
    # Entry cadence. 0 = sequential non-overlapping (enter the next position only after the
    # previous expires). >0 = open a new position every N trading days (overlapping allowed) —
    # a sampling study that yields many more trades on short/active histories.
    entry_every_days: int = 0


@dataclass
class CSPResult:
    trades: list[dict] = field(default_factory=list)
    returns: np.ndarray = field(default_factory=lambda: np.array([]))
    metrics: dict = field(default_factory=dict)


def _asof_price(dates: list, prices: list, d) -> float | None:
    """Last underlying price on or before date d (dates sorted ascending)."""
    pos = bisect.bisect_right(dates, d) - 1
    return float(prices[pos]) if pos >= 0 else None


def _summarize(trades, p, liquidity_skips, u_dates, u_prices):
    """Build the returns array + metrics dict shared by the put- and call-selling backtests.
    `assigned` in a trade means the short option finished ITM (put assigned / shares called)."""
    returns = np.array([t["return"] for t in trades], dtype=float)
    if not returns.size:
        return returns, {}
    total_return = float(np.prod(1.0 + returns) - 1.0)
    entry_vols = [t["entry_volume"] for t in trades if t["entry_volume"] is not None]
    cpy = (252.0 / p.entry_every_days) if p.entry_every_days > 0 else p.cycles_per_year
    metrics = {
        "n_trades": int(returns.size),
        "win_rate": win_rate(returns),
        "assigned_rate": float(np.mean([t["assigned"] for t in trades])),
        "mean_trade_return": float(returns.mean()),
        "total_return": total_return,
        "sharpe_annualized": sharpe_ratio(returns, periods=cpy),
        "max_drawdown": max_drawdown(returns),
        "worst_trade": float(returns.min()),
        "overlapping_samples": p.entry_every_days > 0,
        "bid_fill_rate": float(np.mean([t["fill"] == "bid" for t in trades])),
        "liquidity_skips": liquidity_skips,
        "median_entry_volume": (float(np.median(entry_vols)) if entry_vols else None),
    }
    s0 = _asof_price(u_dates, u_prices, trades[0]["entry"])
    s1 = _asof_price(u_dates, u_prices, trades[-1]["expiry"])
    if s0 and s1 and s0 > 0:
        metrics["benchmark_buy_hold"] = s1 / s0 - 1.0
        metrics["excess_vs_buy_hold"] = total_return - (s1 / s0 - 1.0)
    return returns, metrics


def cash_secured_put_backtest(
    opt_df: pd.DataFrame,
    underlying: pd.Series,
    params: CSPParams | None = None,
    vix: pd.Series | None = None,
) -> CSPResult:
    """Backtest systematic cash-secured put writing.

    opt_df: normalized option chain (see data.sources) with columns
        `date`, `expiry`, `strike`, `kind`, `close`.
    underlying: Series indexed by date -> underlying close price.
    vix: optional VIX series (indexed by date). With params.vix_pct_min/max set, entries are
        gated to the desired regime via a lookahead-free expanding percentile.
    """
    p = params or CSPParams()

    # precompute VIX arrays once for the (optional) regime gate
    vix_gate = vix is not None and (p.vix_pct_min is not None or p.vix_pct_max is not None)
    vix_dates: list = []
    vix_vals: list = []
    if vix_gate:
        vs = vix.sort_index().dropna()
        vix_dates = [x if isinstance(x, date) else pd.Timestamp(x).date() for x in vs.index]
        vix_vals = [float(x) for x in vs.values]

    def _vix_pct(entry) -> float | None:
        pos = bisect.bisect_right(vix_dates, entry) - 1
        if pos < 0:
            return None
        cur, hist = vix_vals[pos], vix_vals[: pos + 1]
        return 100.0 * sum(1 for v in hist if v <= cur) / len(hist)

    d = opt_df
    cols = ["date", "strike", "expiry", "close", "volume", "bid"]
    puts = d[(d["kind"] == "P") & d["close"].notna() & (d["close"] >= p.min_premium)]
    puts = puts[[c for c in cols if c in puts.columns]].dropna(
        subset=["date", "strike", "expiry", "close"])
    for col in ("volume", "bid"):
        if col not in puts.columns:
            puts = puts.assign(**{col: np.nan})
    if puts.empty:
        return CSPResult()

    by_date: dict = {dt: g for dt, g in puts.groupby("date")}
    calendar = sorted(by_date.keys())

    u = underlying.sort_index()
    u_dates = [x if isinstance(x, date) else pd.Timestamp(x).date() for x in u.index]
    u_prices = [float(x) for x in u.values]

    trades: list[dict] = []
    liquidity_skips = 0
    step = p.entry_every_days if p.entry_every_days > 0 else 1
    i = 0
    while i < len(calendar):
        entry = calendar[i]
        spot = _asof_price(u_dates, u_prices, entry)
        if spot is None or spot <= 0:
            i += step
            continue

        if vix_gate:  # sentiment regime filter: skip entries outside the desired VIX percentile
            pct = _vix_pct(entry)
            if (pct is None
                    or (p.vix_pct_min is not None and pct < p.vix_pct_min)
                    or (p.vix_pct_max is not None and pct > p.vix_pct_max)):
                i += step
                continue

        cands = by_date[entry]
        lo = (pd.Timestamp(entry) + pd.Timedelta(days=p.dte_min)).date()
        hi = (pd.Timestamp(entry) + pd.Timedelta(days=p.dte_max)).date()
        cands = cands[(cands["expiry"] >= lo) & (cands["expiry"] <= hi)
                      & (cands["strike"] <= spot)]  # OTM puts only
        if cands.empty:
            i += step
            continue

        # liquidity filter: only count contracts you could plausibly fill that day
        if p.min_contract_volume > 0:
            liquid = cands[cands["volume"].fillna(0) >= p.min_contract_volume]
            if liquid.empty:
                liquidity_skips += 1
                i += step
                continue
            cands = liquid

        target = spot * p.target_moneyness
        pick = cands.iloc[(cands["strike"] - target).abs().argmin()]
        strike, expiry = float(pick["strike"]), pick["expiry"]
        # honest fill: selling-to-open receives the bid; fall back to a slippage haircut on
        # close only when the source has no bid/ask (e.g. Databento OHLCV).
        bid = pick.get("bid")
        if p.use_bid_ask and bid is not None and not pd.isna(bid) and float(bid) > 0:
            premium, fill = float(bid), "bid"
        else:
            premium, fill = float(pick["close"]) * (1.0 - p.slippage_frac), "close-slippage"
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
            "fill": fill, "pnl": round(pnl, 2), "return": ret,
        })

        # advance: by cadence (overlap allowed) or, sequentially, to past this expiry
        i = (i + step) if p.entry_every_days > 0 else bisect.bisect_right(calendar, expiry)

    returns, metrics = _summarize(trades, p, liquidity_skips, u_dates, u_prices)
    return CSPResult(trades=trades, returns=returns, metrics=metrics)


def wheel_backtest(
    opt_df: pd.DataFrame,
    underlying: pd.Series,
    params: CSPParams | None = None,
) -> CSPResult:
    """The full wheel as a state machine on one cash-secured 100-share unit.

    CASH: sell a cash-secured put (target_moneyness). If assigned (S_exp < strike) you buy 100
    shares at basis=strike and switch to SHARES; else keep the premium and stay in CASH.
    SHARES: sell a covered call at >= max(spot, basis) (never lock a loss) near call_moneyness.
    If called away (S_exp > strike) you sell the shares at strike, realize (strike-basis)*100,
    and switch back to CASH; else keep the premium and stay in SHARES. Any shares held at the
    end are marked to the final price. P&L is one connected stream on the initial collateral.
    """
    p = params or CSPParams()

    def _prep(kind: str) -> dict:
        x = opt_df[(opt_df["kind"] == kind) & opt_df["close"].notna()
                   & (opt_df["close"] >= p.min_premium)]
        keep = [c for c in ("date", "strike", "expiry", "close", "volume", "bid") if c in x.columns]
        x = x[keep].dropna(subset=["date", "strike", "expiry", "close"])
        for c in ("volume", "bid"):
            if c not in x.columns:
                x = x.assign(**{c: np.nan})
        return {dt: g for dt, g in x.groupby("date")}

    puts_by, calls_by = _prep("P"), _prep("C")
    calendar = sorted(set(puts_by) | set(calls_by))
    if not calendar:
        return CSPResult()

    u = underlying.sort_index()
    u_dates = [x if isinstance(x, date) else pd.Timestamp(x).date() for x in u.index]
    u_prices = [float(x) for x in u.values]

    def _premium(pick):
        bid = pick.get("bid")
        if p.use_bid_ask and bid is not None and not pd.isna(bid) and float(bid) > 0:
            return float(bid), "bid"
        return float(pick["close"]) * (1.0 - p.slippage_frac), "close-slippage"

    def _liquid(c):
        return c[c["volume"].fillna(0) >= p.min_contract_volume] if p.min_contract_volume > 0 else c

    trades: list[dict] = []
    cum_pnl, initial_collateral = 0.0, None
    equity = []  # cumulative pnl after each cycle
    state, basis = "CASH", None
    i = 0
    while i < len(calendar):
        day = calendar[i]
        spot = _asof_price(u_dates, u_prices, day)
        if spot is None or spot <= 0:
            i += 1
            continue
        lo = (pd.Timestamp(day) + pd.Timedelta(days=p.dte_min)).date()
        hi = (pd.Timestamp(day) + pd.Timedelta(days=p.dte_max)).date()

        if state == "CASH":
            c = puts_by.get(day)
            if c is None:
                i += 1
                continue
            c = _liquid(c[(c["expiry"] >= lo) & (c["expiry"] <= hi) & (c["strike"] <= spot)])
            if c.empty:
                i += 1
                continue
            pick = c.iloc[(c["strike"] - spot * p.target_moneyness).abs().argmin()]
            strike, expiry = float(pick["strike"]), pick["expiry"]
            premium, fill = _premium(pick)
            s_exp = _asof_price(u_dates, u_prices, expiry)
            if s_exp is None:
                break
            if initial_collateral is None:
                initial_collateral = strike * 100.0
            assigned = s_exp < strike
            cyc = premium * 100.0 - p.commission_per_contract * (2 if assigned else 1)
            if assigned:
                basis, state = strike, "SHARES"
            leg = "put"
        else:  # SHARES -> sell a covered call that won't lock a loss
            c = calls_by.get(day)
            if c is None:
                i += 1
                continue
            floor = max(spot, basis)
            c = _liquid(c[(c["expiry"] >= lo) & (c["expiry"] <= hi) & (c["strike"] >= floor)])
            if c.empty:
                i += 1
                continue
            pick = c.iloc[(c["strike"] - spot * p.call_moneyness).abs().argmin()]
            strike, expiry = float(pick["strike"]), pick["expiry"]
            premium, fill = _premium(pick)
            s_exp = _asof_price(u_dates, u_prices, expiry)
            if s_exp is None:
                break
            called = s_exp > strike
            cyc = premium * 100.0 - p.commission_per_contract * (2 if called else 1)
            if called:
                cyc += (strike - basis) * 100.0
                basis, state = None, "CASH"
            leg = "call"

        cum_pnl += cyc
        equity.append(cum_pnl)
        trades.append({"leg": leg, "entry": day, "expiry": expiry, "spot": round(spot, 2),
                       "strike": strike, "premium": round(premium, 4),
                       "underlying_at_expiry": round(s_exp, 2),
                       "assigned": (assigned if leg == "put" else called), "fill": fill,
                       "pnl": round(cyc, 2), "return": cyc / (initial_collateral or 1.0)})
        i = bisect.bisect_right(calendar, expiry)

    if not trades or not initial_collateral:
        return CSPResult()
    if state == "SHARES" and basis is not None:  # mark remaining shares to the last price
        final = _asof_price(u_dates, u_prices, calendar[-1])
        if final is not None:
            cum_pnl += (final - basis) * 100.0
            equity.append(cum_pnl)

    equity_curve = np.array([initial_collateral] + [initial_collateral + e for e in equity])
    step_returns = np.diff(equity_curve) / equity_curve[:-1]
    metrics = {
        "n_trades": len(trades),
        "put_sales": sum(t["leg"] == "put" for t in trades),
        "call_sales": sum(t["leg"] == "call" for t in trades),
        "assignments": sum(t["leg"] == "put" and t["assigned"] for t in trades),
        "called_away": sum(t["leg"] == "call" and t["assigned"] for t in trades),
        "win_rate": float(np.mean([t["pnl"] > 0 for t in trades])),
        "total_return": float(equity_curve[-1] / initial_collateral - 1.0),
        "sharpe_annualized": sharpe_ratio(step_returns, periods=p.cycles_per_year),
        "max_drawdown": max_drawdown(step_returns),
        "bid_fill_rate": float(np.mean([t["fill"] == "bid" for t in trades])),
    }
    s0 = _asof_price(u_dates, u_prices, trades[0]["entry"])
    s1 = _asof_price(u_dates, u_prices, trades[-1]["expiry"])
    if s0 and s1 and s0 > 0:
        metrics["benchmark_buy_hold"] = s1 / s0 - 1.0
        metrics["excess_vs_buy_hold"] = metrics["total_return"] - (s1 / s0 - 1.0)
    return CSPResult(trades=trades, returns=step_returns, metrics=metrics)


def covered_call_backtest(
    opt_df: pd.DataFrame,
    underlying: pd.Series,
    params: CSPParams | None = None,
) -> CSPResult:
    """Backtest systematic covered-call writing (the wheel's second leg).

    Each cycle: hold 100 shares (basis = spot at entry) and sell one OTM call held to expiry.
    Per-share P&L = min(S_exp, strike) - spot + premium (upside capped at the strike), so the
    position keeps the stock's downside minus the premium cushion. `target_moneyness` here is
    the call strike as a multiple of spot (>1 = OTM, e.g. 1.05).
    """
    p = params or CSPParams()
    d = opt_df
    cols = ["date", "strike", "expiry", "close", "volume", "bid"]
    calls = d[(d["kind"] == "C") & d["close"].notna() & (d["close"] >= p.min_premium)]
    calls = calls[[c for c in cols if c in calls.columns]].dropna(
        subset=["date", "strike", "expiry", "close"])
    for col in ("volume", "bid"):
        if col not in calls.columns:
            calls = calls.assign(**{col: np.nan})
    if calls.empty:
        return CSPResult()

    by_date = {dt: g for dt, g in calls.groupby("date")}
    calendar = sorted(by_date.keys())
    u = underlying.sort_index()
    u_dates = [x if isinstance(x, date) else pd.Timestamp(x).date() for x in u.index]
    u_prices = [float(x) for x in u.values]

    trades, liquidity_skips = [], 0
    step = p.entry_every_days if p.entry_every_days > 0 else 1
    i = 0
    while i < len(calendar):
        entry = calendar[i]
        spot = _asof_price(u_dates, u_prices, entry)
        if spot is None or spot <= 0:
            i += step
            continue
        cands = by_date[entry]
        lo = (pd.Timestamp(entry) + pd.Timedelta(days=p.dte_min)).date()
        hi = (pd.Timestamp(entry) + pd.Timedelta(days=p.dte_max)).date()
        cands = cands[(cands["expiry"] >= lo) & (cands["expiry"] <= hi)
                      & (cands["strike"] >= spot)]  # OTM calls only
        if cands.empty:
            i += step
            continue
        if p.min_contract_volume > 0:
            liquid = cands[cands["volume"].fillna(0) >= p.min_contract_volume]
            if liquid.empty:
                liquidity_skips += 1
                i += step
                continue
            cands = liquid

        target = spot * p.target_moneyness
        pick = cands.iloc[(cands["strike"] - target).abs().argmin()]
        strike, expiry = float(pick["strike"]), pick["expiry"]
        bid = pick.get("bid")
        if p.use_bid_ask and bid is not None and not pd.isna(bid) and float(bid) > 0:
            premium, fill = float(bid), "bid"
        else:
            premium, fill = float(pick["close"]) * (1.0 - p.slippage_frac), "close-slippage"
        entry_volume = pick["volume"]

        s_exp = _asof_price(u_dates, u_prices, expiry)
        if s_exp is None:
            break
        called_away = s_exp > strike
        commissions = p.commission_per_contract * (2 if called_away else 1)
        interest = 0.0  # covered call capital is in shares, not cash collateral
        # per-share: stock marked at min(S_exp, strike) (called away at strike) minus basis, + premium
        pnl = (min(s_exp, strike) - spot + premium) * 100.0 - commissions + interest
        collateral = spot * 100.0
        ret = pnl / collateral
        trades.append({
            "entry": entry, "expiry": expiry, "spot": round(spot, 2), "strike": strike,
            "premium": round(premium, 4), "underlying_at_expiry": round(s_exp, 2),
            "assigned": called_away, "entry_volume": (None if pd.isna(entry_volume) else int(entry_volume)),
            "fill": fill, "pnl": round(pnl, 2), "return": ret,
        })
        i = (i + step) if p.entry_every_days > 0 else bisect.bisect_right(calendar, expiry)

    returns, metrics = _summarize(trades, p, liquidity_skips, u_dates, u_prices)
    return CSPResult(trades=trades, returns=returns, metrics=metrics)
