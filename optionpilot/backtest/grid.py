"""Grid-trading backtest for USDⓈ-M perpetuals (long-only grid, incl. US-stock perps).

A grid bot places buy orders below and sell orders above the price on a ladder of levels; each
buy that is later sold one level up books a fixed price-step profit. It MINTS money in a
sideways/oscillating market and BLEEDS in a trend — especially a downtrend, where it keeps
"catching the knife", accumulating inventory at a loss. This engine exists to quantify that
honestly: it separates booked grid profit from the marked-to-market loss on stuck inventory,
reports how long price spent OUTSIDE the grid, and benchmarks against simply buying & holding.

Modeling choices (deliberately conservative / lookahead-free where it matters):
- Fills are detected close-to-close (a level fills when consecutive closes straddle it). This
  UNDER-counts intrabar oscillation, so use a fine interval (e.g. 15m/1h). It never cheats by
  assuming a favourable intrabar path.
- Long-only: an initial position is bought to back the sell orders above the start price; the
  grid never goes net short.
- Costs are explicit: a per-fill fee and an optional funding drag on the held long inventory.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class GridParams:
    lower: float | None = None         # grid bottom; None -> 10th percentile of window (lookahead!)
    upper: float | None = None         # grid top;    None -> 90th percentile of window (lookahead!)
    n_grids: int = 20                  # number of grid LINES
    capital: float = 10_000.0          # USDT budget (sizes the per-grid quantity)
    fee_rate: float = 0.0002           # per fill, fraction (2 bps ~ Binance USDⓈ-M maker)
    spacing: str = "arith"             # "arith" (equal $ step) or "geom" (equal % step)
    funding_per_8h: float | None = None  # mean funding rate per 8h; applied as a long-carry drag
    # Optional VIX regime gate: when a `vix` series is passed, only ADD inventory (fill buys) on a
    # bar whose VIX expanding-percentile (lookahead-free) is <= this. Sells are always allowed, so
    # the grid de-risks but stops catching the knife when equity fear is high. None = no gate.
    vix_pct_max: float | None = None


def _grid_lines(lower: float, upper: float, n: int, spacing: str) -> np.ndarray:
    if spacing == "geom":
        return np.geomspace(lower, upper, n)
    return np.linspace(lower, upper, n)


def _drawdown(equity: np.ndarray) -> float:
    if equity.size == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    return float((equity / peak - 1.0).min())


def grid_backtest(klines: pd.DataFrame, p: GridParams, vix: pd.Series | None = None) -> dict:
    """Run the long-only grid over a klines frame (needs a 'close' column, time-sorted index).

    vix: optional VIX series (by date). With params.vix_pct_max set, new buys are gated to
    calm-regime bars (lookahead-free expanding percentile); sells are never gated."""
    if klines is None or klines.empty or "close" not in klines:
        return {"ran": False, "reason": "沒有 K 線資料"}
    closes = klines["close"].astype(float).to_numpy()
    times = list(klines.index)
    if closes.size < 3:
        return {"ran": False, "reason": "K 線太少,無法回測"}

    # optional VIX regime gate: precompute one expanding-percentile per bar date (no lookahead)
    vix_gate = vix is not None and p.vix_pct_max is not None
    pct_by_date: dict = {}
    if vix_gate:
        from optionpilot.sentiment import expanding_pct_rank
        for ts in times:
            d = ts.date() if hasattr(ts, "date") else ts
            if d not in pct_by_date:
                pct_by_date[d] = expanding_pct_rank(vix, d)
    n_buys_gated = 0

    start_px = float(closes[0])
    auto_range = p.lower is None or p.upper is None
    lower = p.lower if p.lower is not None else float(np.percentile(closes, 10))
    upper = p.upper if p.upper is not None else float(np.percentile(closes, 90))
    if not (upper > lower > 0):
        return {"ran": False, "reason": f"區間無效 lower={lower} upper={upper}"}

    lines = _grid_lines(lower, upper, p.n_grids, p.spacing)
    idx_of = {round(float(v), 10): i for i, v in enumerate(lines)}
    lines_sorted = [float(v) for v in lines]

    # per-grid quantity: hold ALL lines ~= capital of notional at the start price
    qty = p.capital / (p.n_grids * start_px)

    # bar duration (hours) for the funding drag
    bar_h = 8.0
    if hasattr(klines.index, "to_series") and len(klines.index) > 1:
        d = klines.index.to_series().diff().dropna().dt.total_seconds()
        if len(d):
            bar_h = float(np.median(d)) / 3600.0 or 8.0

    # --- initial state: prefill inventory to back sell orders above the start price ---
    above = [ln for ln in lines_sorted if ln > start_px]
    below = [ln for ln in lines_sorted if ln < start_px]
    inventory: list[float] = [start_px] * len(above)   # cost basis of each held unit
    cash = p.capital - qty * start_px * len(above) * (1 + p.fee_rate)
    fees = qty * start_px * len(above) * p.fee_rate
    buy_orders = set(below)
    sell_orders = set(above)

    realized = 0.0          # booked grid profit, gross of fees
    funding_paid = 0.0
    n_buys = n_sells = 0
    equity_curve = [cash + len(inventory) * qty * start_px]
    n_below_range = 0
    n_in_range = 0

    prev = start_px
    for k in range(1, len(closes)):
        cur = float(closes[k])
        # VIX regime gate: in a high-fear bar, stop ADDING inventory (but still allow sells below)
        buys_allowed = True
        if vix_gate:
            pct = pct_by_date.get(times[k].date() if hasattr(times[k], "date") else times[k])
            buys_allowed = pct is not None and pct <= p.vix_pct_max
        if cur < prev:   # falling -> fill buy orders between cur and prev, top-down
            for lvl in sorted([b for b in buy_orders if cur <= b < prev], reverse=True):
                if not buys_allowed:
                    n_buys_gated += 1
                    continue
                cost = qty * lvl
                cash -= cost * (1 + p.fee_rate)
                fees += cost * p.fee_rate
                inventory.append(lvl)
                buy_orders.discard(lvl)
                n_buys += 1
                i = idx_of[round(lvl, 10)]
                if i + 1 < len(lines_sorted):
                    sell_orders.add(lines_sorted[i + 1])
        elif cur > prev:  # rising -> fill sell orders between prev and cur, bottom-up
            for lvl in sorted([s for s in sell_orders if prev < s <= cur]):
                if not inventory:
                    continue
                buy_price = inventory.pop(0)   # FIFO; grid pairs it with the level one step down
                proceeds = qty * lvl
                cash += proceeds * (1 - p.fee_rate)
                fees += proceeds * p.fee_rate
                realized += qty * (lvl - buy_price)
                sell_orders.discard(lvl)
                n_sells += 1
                i = idx_of[round(lvl, 10)]
                if i - 1 >= 0:
                    buy_orders.add(lines_sorted[i - 1])

        # funding drag on the held long inventory
        if p.funding_per_8h:
            notional = len(inventory) * qty * cur
            f = notional * p.funding_per_8h * (bar_h / 8.0)
            cash -= f
            funding_paid += f

        n_below_range += int(cur < lower)
        n_in_range += int(lower <= cur <= upper)
        equity_curve.append(cash + len(inventory) * qty * cur)
        prev = cur

    eq = np.asarray(equity_curve, dtype=float)
    end_px = float(closes[-1])
    inv_units = len(inventory)
    inv_cost = float(sum(inventory) * qty)
    inv_value = inv_units * qty * end_px
    final_equity = float(eq[-1])
    n_bars = len(closes)

    return {
        "ran": True,
        "lower": round(lower, 4), "upper": round(upper, 4),
        "auto_range_in_sample": auto_range,   # True => range used lookahead; optimistic, flag it
        "n_grids": p.n_grids, "spacing": p.spacing,
        "qty_per_grid": round(qty, 6),
        "start_price": round(start_px, 4), "end_price": round(end_px, 4),
        "n_buys": n_buys, "n_sells": n_sells, "n_roundtrips": n_sells,
        "realized_grid_pnl": round(realized, 2),
        "fees_paid": round(fees, 2),
        "funding_paid": round(funding_paid, 2),
        "open_inventory_units": inv_units,
        "open_inventory_value": round(inv_value, 2),
        "open_unrealized_pnl": round(inv_value - inv_cost, 2),
        "final_equity": round(final_equity, 2),
        "total_return": round(final_equity / p.capital - 1.0, 4),
        "buy_hold_return": round(end_px / start_px - 1.0, 4),
        "excess_vs_buy_hold": round((final_equity / p.capital - 1.0) - (end_px / start_px - 1.0), 4),
        "max_drawdown": round(_drawdown(eq), 4),
        "pct_time_in_range": round(100.0 * n_in_range / n_bars, 1),
        "pct_time_below_lower": round(100.0 * n_below_range / n_bars, 1),
        "n_bars": n_bars,
        "vix_gated": vix_gate,
        "buys_skipped_by_vix": n_buys_gated,
        "_equity_curve": eq,    # for charting; tools strip the leading underscore keys
    }
