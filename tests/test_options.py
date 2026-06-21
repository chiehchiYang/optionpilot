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


# --- unusual activity (normalized schema) ------------------------------------
def _vol_frame():
    rows = [{"date": date(2024, 1, d), "contract": "PUT1", "kind": "P", "volume": v}
            for d, v in zip(range(2, 12), [10, 12, 9, 11, 8, 10, 13, 9, 10, 300])]
    rows += [{"date": date(2024, 1, 2), "contract": "CALL1", "kind": "C", "volume": 50}]
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


def test_unusual_volume_no_volume_column_is_empty():
    # a source without volume (e.g. DoltHub) -> no flags, no crash
    df = pd.DataFrame([{"date": date(2024, 1, 2), "contract": "X", "kind": "P", "volume": float("nan")}])
    assert unusual_volume(df).empty


# --- cash-secured put backtest (normalized schema) ---------------------------
def _csp_inputs(s_expiry):
    opt = pd.DataFrame([{
        "date": date(2024, 1, 2), "contract": "NOK240201P4500",
        "expiry": date(2024, 2, 1), "strike": 4.5, "kind": "P",
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


def test_csp_liquidity_filter_picks_liquid_contract():
    opt = pd.DataFrame([
        {"date": date(2024, 1, 2), "contract": "P45", "expiry": date(2024, 2, 1),
         "strike": 4.5, "kind": "P", "close": 0.20, "volume": 5},     # closest but thin
        {"date": date(2024, 1, 2), "contract": "P40", "expiry": date(2024, 2, 1),
         "strike": 4.0, "kind": "P", "close": 0.10, "volume": 100},   # liquid
    ])
    u = pd.Series({date(2024, 1, 2): 5.0, date(2024, 2, 1): 5.5})
    # no filter -> picks strike closest to 4.75 = 4.5 (thin, vol 5)
    r0 = cash_secured_put_backtest(opt, u, CSPParams(min_contract_volume=0))
    assert r0.trades[0]["strike"] == 4.5 and r0.trades[0]["entry_volume"] == 5
    # filter >=50 -> 4.5 excluded, falls to liquid 4.0 (vol 100)
    r1 = cash_secured_put_backtest(opt, u, CSPParams(min_contract_volume=50))
    assert r1.trades[0]["strike"] == 4.0 and r1.trades[0]["entry_volume"] == 100
    assert r1.metrics["median_entry_volume"] == 100.0


def test_csp_entry_cadence_generates_more_trades():
    # 60 DAILY entries, each a 30-day OTM put. Sequential (jump past expiry) opens ~2;
    # cadence every 5 trading days opens many more (overlapping samples).
    import pandas as pd
    from datetime import timedelta
    rows, u = [], {}
    d0 = date(2024, 1, 1)
    for k in range(60):
        entry = d0 + timedelta(days=k)
        rows.append({"date": entry, "contract": f"P{k}", "expiry": entry + timedelta(days=30),
                     "strike": 95.0, "kind": "P", "close": 1.0, "volume": 100})
    cur, last = d0, d0 + timedelta(days=95)
    while cur <= last:
        u[cur] = 100.0          # flat underlying, puts expire OTM (keep premium)
        cur += timedelta(days=1)
    opt = pd.DataFrame(rows)
    under = pd.Series(u).sort_index()
    seq = cash_secured_put_backtest(opt, under, CSPParams(entry_every_days=0))
    wk = cash_secured_put_backtest(opt, under, CSPParams(entry_every_days=5))
    assert wk.metrics["n_trades"] > seq.metrics["n_trades"]
    assert wk.metrics["overlapping_samples"] is True


def test_csp_collateral_interest_adds_return():
    opt, u = _csp_inputs(s_expiry=5.5)  # worthless put, base pnl 18.35
    r0 = cash_secured_put_backtest(opt, u, CSPParams())
    r1 = cash_secured_put_backtest(opt, u, CSPParams(risk_free_rate=0.05))
    interest = 450 * 0.05 * 30 / 365  # collateral 450, 30 days held
    # pnl is rounded to 2dp in the trade record
    assert r1.trades[0]["pnl"] == pytest.approx(r0.trades[0]["pnl"] + interest, abs=0.01)
