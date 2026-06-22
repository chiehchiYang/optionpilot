"""Tests for VRP analysis (realized vol split + implied vol recovery via our solver)."""

from datetime import date, timedelta

import pandas as pd
import pytest

from optionpilot.analysis import measure_vrp, realized_vol, support_resistance
from optionpilot.data.greeks import black_scholes_price


def test_realized_vol_splits_up_down():
    # alternating +1% / -2% daily moves
    idx = [date(2024, 1, 1) + timedelta(days=k) for k in range(20)]
    px = [100.0]
    for k in range(1, 20):
        px.append(px[-1] * (1.01 if k % 2 else 0.98))
    rv = realized_vol(pd.Series(px, index=idx))
    assert rv["downside_vol"] > rv["upside_vol"]   # -2% moves bigger than +1%
    assert rv["up_days"] + rv["down_days"] == 19


def test_support_resistance_levels():
    # V-shaped path: dips to a low (support) then recovers; current price mid-way up
    lows = list(range(50, 30, -1)) + list(range(30, 45))     # 50->30->44
    ohlc = pd.DataFrame({
        "High": [x + 1 for x in lows],
        "Low": [x - 1 for x in lows],
        "Close": lows,
    })
    res = support_resistance(ohlc, lookback=120, swing_window=3)
    cur = res["current_price"]
    assert res["recent_low"] <= cur <= res["recent_high"]
    assert all(s < cur for s in res["swing_supports"])        # supports below price
    assert all(r > cur for r in res["swing_resistances"])     # resistances above price
    assert {"P", "S1", "R1"} <= set(res["pivots"])            # pivot levels present


def test_measure_vrp_recovers_known_iv():
    # build options priced at a KNOWN 40% vol; measure_vrp's implied vol should recover ~0.40
    true_iv, spot, r = 0.40, 100.0, 0.05
    idx = [date(2024, 1, 1) + timedelta(days=k) for k in range(30)]
    under = pd.Series([spot] * 30, index=idx)   # flat underlying -> ~0 realized vol
    rows = []
    for d in idx:
        exp = d + timedelta(days=30)
        for strike in (95.0, 100.0, 105.0):
            price = black_scholes_price(spot, strike, 30 / 365, r, true_iv, "put")
            rows.append({"date": d, "contract": f"{strike}", "expiry": exp, "strike": strike,
                         "kind": "P", "close": price, "volume": 100})
    res = measure_vrp(pd.DataFrame(rows), under, rate=r)
    assert res["implied_vol"] == pytest.approx(0.40, abs=0.02)
    assert res["realized_vol"] == pytest.approx(0.0, abs=1e-6)
    assert res["vrp_total"] > 0.3   # IV 40% vs ~0 realized -> big positive VRP
