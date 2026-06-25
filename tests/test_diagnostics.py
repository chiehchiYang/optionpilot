"""Tests for backtest diagnostics: tell a by-design low-trade run from thin data / liquidity."""

from datetime import date, timedelta

import pandas as pd

from optionpilot.backtest.strategies import (
    CSPParams,
    cash_secured_put_backtest,
    covered_call_backtest,
)


def _put_chain(n_days=120, dte=30, strike=95.0, volume=100):
    start = date(2024, 1, 1)
    dates = [start + timedelta(days=k) for k in range(n_days)]
    rows = [{"date": d, "expiry": d + timedelta(days=dte), "strike": strike, "kind": "P",
             "close": 1.0, "volume": volume, "bid": 1.0} for d in dates]
    under = pd.Series([100.0] * n_days, index=dates)        # flat, spot 100 -> 95 puts OTM
    return pd.DataFrame(rows), under


def _params(**kw):
    return CSPParams(min_premium=0.01, **kw)


def test_diagnostics_present_with_chain_coverage():
    opt, under = _put_chain(n_days=120)
    res = cash_secured_put_backtest(opt, under, _params(min_contract_volume=0))
    d = res.diagnostics
    assert d["trades_made"] == res.metrics["n_trades"]
    assert d["chain_coverage"]["n_chain_dates"] == 120
    assert d["chain_coverage"]["n_strikes"] == 1
    assert d["chain_coverage"]["n_rows"] == 120


def test_by_design_low_trade_reason():
    opt, under = _put_chain(n_days=120, dte=30)             # non-overlapping 30-DTE
    res = cash_secured_put_backtest(opt, under, _params(min_contract_volume=0))
    assert res.diagnostics["skips"]["no_contract_in_dte_window"] == 0
    assert "非重疊" in res.diagnostics["low_trade_count_reason"]


def test_thin_data_reason_when_expiries_outside_window():
    opt, under = _put_chain(n_days=90, dte=90)              # 90-DTE never in default 25-45 window
    res = cash_secured_put_backtest(opt, under, _params(min_contract_volume=0))
    assert res.metrics == {}                                # no trades
    d = res.diagnostics
    assert d["skips"]["no_contract_in_dte_window"] >= 1
    assert "資料覆蓋不足" in d["low_trade_count_reason"]


def test_liquidity_reason_when_volume_below_threshold():
    opt, under = _put_chain(n_days=90, dte=30, volume=100)
    res = cash_secured_put_backtest(opt, under, _params(min_contract_volume=1000))
    assert res.metrics == {}
    d = res.diagnostics
    assert d["skips"]["liquidity"] >= 1
    assert "流動性" in d["low_trade_count_reason"]


def test_covered_call_also_has_diagnostics():
    start = date(2024, 1, 1)
    dates = [start + timedelta(days=k) for k in range(90)]
    rows = [{"date": d, "expiry": d + timedelta(days=30), "strike": 105.0, "kind": "C",
             "close": 1.0, "volume": 100, "bid": 1.0} for d in dates]
    under = pd.Series([100.0] * 90, index=dates)
    res = covered_call_backtest(pd.DataFrame(rows), under,
                                _params(target_moneyness=1.05, min_contract_volume=0))
    assert "low_trade_count_reason" in res.diagnostics
    assert res.diagnostics["chain_coverage"]["n_strikes"] == 1
