"""Tests for the grid backtest: it should PROFIT in a range and BLEED in a downtrend."""

import numpy as np
import pandas as pd

from optionpilot.backtest.grid import GridParams, grid_backtest


def _klines(prices):
    idx = pd.to_datetime(np.arange(len(prices)) * 3600_000, unit="ms", utc=True)
    return pd.DataFrame({"close": prices}, index=idx)


def test_grid_profits_in_oscillating_range():
    # sawtooth oscillating 90<->110 around a flat mean -> grid books roundtrips, ~no trend
    osc = [100 + 10 * np.sin(i / 2.0) for i in range(400)]
    res = grid_backtest(_klines(osc), GridParams(lower=90, upper=110, n_grids=20,
                                                 capital=10000, fee_rate=0.0))
    assert res["ran"]
    assert res["n_roundtrips"] > 0
    assert res["realized_grid_pnl"] > 0          # booked grid profit in a range
    # ends near where it started -> grid should beat buy&hold (which is ~flat)
    assert res["total_return"] > res["buy_hold_return"] - 1e-6


def test_grid_bleeds_and_gets_stuck_in_downtrend():
    # straight downtrend through and below the grid -> catches the knife, stuck inventory
    down = list(np.linspace(110, 60, 300))
    res = grid_backtest(_klines(down), GridParams(lower=90, upper=110, n_grids=20,
                                                  capital=10000, fee_rate=0.0002))
    assert res["ran"]
    assert res["open_inventory_units"] > 0        # left holding inventory
    assert res["open_unrealized_pnl"] < 0         # marked-to-market loss on stuck inventory
    assert res["pct_time_below_lower"] > 0        # price spent time below the grid
    assert res["total_return"] < 0                # the bot lost money


def test_auto_range_is_flagged():
    res = grid_backtest(_klines([100 + (i % 5) for i in range(50)]),
                        GridParams(lower=None, upper=None, n_grids=10))
    assert res["auto_range_in_sample"] is True    # lookahead range must be flagged


def test_funding_drag_reduces_return():
    osc = [100 + 8 * np.sin(i / 3.0) for i in range(300)]
    base = grid_backtest(_klines(osc), GridParams(lower=92, upper=108, n_grids=16, fee_rate=0.0))
    drag = grid_backtest(_klines(osc), GridParams(lower=92, upper=108, n_grids=16, fee_rate=0.0,
                                                  funding_per_8h=0.001))  # 0.1%/8h long pays
    assert drag["funding_paid"] > 0
    assert drag["final_equity"] < base["final_equity"]
