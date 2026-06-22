"""Tests for the Binance perp data parsing + funding-carry analysis (no network)."""

import numpy as np
import pandas as pd

from optionpilot import crypto
from optionpilot.data import binance

_8H_MS = 8 * 3600 * 1000


def _funding_raw(rates, start_ms=1_700_000_000_000):
    return [{"symbol": "NOKUSDT", "fundingTime": start_ms + i * _8H_MS,
             "fundingRate": f"{r:.8f}", "markPrice": "13.5"} for i, r in enumerate(rates)]


def test_funding_history_parses(monkeypatch):
    monkeypatch.setattr(binance, "_get", lambda *a, **k: _funding_raw([0.0001, -0.0002, 0.0003]))
    df = binance.funding_rate_history("nokusdt")
    assert list(df.columns) == ["funding_time", "funding_rate"]
    assert len(df) == 3
    assert df["funding_rate"].tolist() == [0.0001, -0.0002, 0.0003]
    assert df["funding_time"].is_monotonic_increasing


def test_funding_summary_positive_means_shorts_earn():
    # persistently positive funding -> longs pay shorts -> favoured side is short the perp
    df = pd.DataFrame({
        "funding_time": pd.to_datetime(np.arange(30) * _8H_MS, unit="ms", utc=True),
        "funding_rate": [0.0001] * 30,   # 0.01% every 8h
    })
    res = crypto.funding_summary(df)
    assert res["interval_hours"] == 8.0
    assert res["events_per_year"] == 1095.0
    assert res["direction"] == "longs_pay_shorts"
    assert res["carry_side"] == "short_perp"
    # 0.0001 * 3 * 365 = 0.10905 -> ~10.9%/yr
    assert res["annualized_funding_pct"] == 10.95
    assert res["pct_intervals_positive"] == 100.0


def test_funding_summary_negative_flips_side():
    df = pd.DataFrame({
        "funding_time": pd.to_datetime(np.arange(10) * _8H_MS, unit="ms", utc=True),
        "funding_rate": [-0.0005] * 10,
    })
    res = crypto.funding_summary(df)
    assert res["direction"] == "shorts_pay_longs"
    assert res["carry_side"] == "long_perp"
    assert res["annualized_funding"] < 0


def test_klines_parses(monkeypatch):
    rows = [[1_700_000_000_000 + i * 3600_000, "10", "12", "9", "11", "100",
             1_700_000_003_599, "1100", 50, "60", "660", "0"] for i in range(5)]
    monkeypatch.setattr(binance, "_get", lambda *a, **k: rows)
    df = binance.klines("btcusdt", interval="1h", limit=5)
    assert len(df) == 5
    assert df["close"].iloc[0] == 11.0
    assert df["trades"].iloc[0] == 50
    rv = crypto.realized_vol_from_klines(df)
    assert rv["bars"] == 4
    assert rv["periods_per_year"] == 24 * 365
