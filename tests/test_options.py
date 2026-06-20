"""Tests for OSI parsing, unusual-activity signals, and the cash-secured put backtest."""

from datetime import date

import pandas as pd
import pytest

from optionpilot.backtest.strategies import CSPParams, cash_secured_put_backtest
from optionpilot.data.osi import parse_osi, try_parse_osi
from optionpilot.signals import daily_put_call_ratio, unusual_volume


# --- OSI ---------------------------------------------------------------------
def test_parse_osi_call_and_put():
    c = parse_osi("NOK   230113C00005000")
    assert c.root == "NOK" and c.expiry == date(2023, 1, 13) and c.is_call and c.strike == 5.0
    p = parse_osi("NOK   240201P00004500")
    assert p.is_put and p.strike == 4.5 and p.expiry == date(2024, 2, 1)


def test_parse_osi_malformed():
    with pytest.raises(ValueError):
        parse_osi("not-a-symbol")
    assert try_parse_osi("garbage") is None


# --- unusual activity --------------------------------------------------------
def _vol_frame():
    sym = "NOK   240201P00004500"
    rows = [{"date": date(2024, 1, d), "symbol": sym, "volume": v}
            for d, v in zip(range(2, 12), [10, 12, 9, 11, 8, 10, 13, 9, 10, 300])]
    # add a few call rows for the put/call ratio test
    rows += [{"date": date(2024, 1, 2), "symbol": "NOK   240201C00006000", "volume": 50}]
    return pd.DataFrame(rows)


def test_unusual_volume_flags_spike():
    flagged = unusual_volume(_vol_frame(), lookback=20, ratio_threshold=3.0, min_volume=50)
    assert len(flagged) == 1
    assert flagged.iloc[0]["volume"] == 300 and flagged.iloc[0]["ratio"] > 3


def test_put_call_ratio():
    pcr = daily_put_call_ratio(_vol_frame())
    row = pcr.loc[date(2024, 1, 2)]
    assert row["put_volume"] == 10 and row["call_volume"] == 50
    assert row["put_call_ratio"] == pytest.approx(0.2)


# --- cash-secured put backtest ----------------------------------------------
def _csp_inputs(s_expiry):
    opt = pd.DataFrame([{
        "date": date(2024, 1, 2), "symbol": "NOK   240201P00004500",
        "close": 0.20, "volume": 100,
    }])
    underlying = pd.Series({date(2024, 1, 2): 5.0, date(2024, 2, 1): s_expiry})
    return opt, underlying


def test_csp_put_expires_worthless_keeps_premium():
    opt, u = _csp_inputs(s_expiry=5.5)  # above strike 4.5 -> not assigned
    res = cash_secured_put_backtest(opt, u, CSPParams())
    assert len(res.trades) == 1
    t = res.trades[0]
    assert t["assigned"] is False
    # premium 0.20*(1-0.05)=0.19 -> 19.0 - 0.65 commission = 18.35
    assert t["pnl"] == pytest.approx(18.35, abs=1e-6)
    assert t["return"] == pytest.approx(18.35 / 450.0, abs=1e-9)
    assert res.metrics["win_rate"] == 1.0
    # buy-and-hold benchmark: 5.0 -> 5.5 = +10%, which beats the +4.08% CSP cycle
    assert res.metrics["benchmark_buy_hold"] == pytest.approx(0.10, abs=1e-9)
    assert res.metrics["excess_vs_buy_hold"] < 0


def test_csp_put_assigned_takes_loss():
    opt, u = _csp_inputs(s_expiry=4.0)  # below strike 4.5 -> assigned, intrinsic 0.5
    res = cash_secured_put_backtest(opt, u, CSPParams())
    t = res.trades[0]
    assert t["assigned"] is True
    # (0.19 - 0.5)*100 - 2*0.65 = -31 - 1.3 = -32.3
    assert t["pnl"] == pytest.approx(-32.3, abs=1e-6)
    assert res.metrics["worst_trade"] < 0


def test_csp_no_candidates_returns_empty():
    opt, u = _csp_inputs(s_expiry=5.5)
    # require DTE far outside the contract's 30-day window -> no candidates
    res = cash_secured_put_backtest(opt, u, CSPParams(dte_min=60, dte_max=90))
    assert res.trades == [] and res.returns.size == 0
