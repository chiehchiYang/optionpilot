"""Test ThetaData v3 option-EOD normalization (no live terminal needed — uses mock rows)."""

from datetime import date

import pytest

from optionpilot.data.sources import NORMALIZED_COLUMNS, _date_chunks, _normalize_thetadata


def test_date_chunks_respects_365_cap():
    chunks = list(_date_chunks("2024-01-01", "2026-06-18", max_days=365))
    assert len(chunks) == 3                         # ~2.5yr -> 3 windows
    assert chunks[0][0] == "2024-01-01"
    assert chunks[-1][1] == "2026-06-18"
    # contiguous, non-overlapping, each <= 365 days
    for (s, e) in chunks:
        assert (date.fromisoformat(e) - date.fromisoformat(s)).days <= 364
    for (s1, e1), (s2, e2) in zip(chunks, chunks[1:]):
        assert (date.fromisoformat(s2) - date.fromisoformat(e1)).days == 1


def _row(**kw):
    base = {"symbol": "ZETA", "expiration": "2024-07-19", "strike": 5.0, "right": "PUT",
            "close": 0.20, "volume": 37, "bid": 0.18, "ask": 0.22,
            "created": "2024-01-03T17:18:57.972", "last_trade": "2024-01-03T10:00:00.000"}
    base.update(kw)
    return base


def test_normalize_thetadata_v3_basic():
    df = _normalize_thetadata([_row()])
    assert list(df.columns) == NORMALIZED_COLUMNS
    r = df.iloc[0]
    assert r["date"] == date(2024, 1, 3)          # from `created` day
    assert r["expiry"] == date(2024, 7, 19)
    assert r["strike"] == 5.0 and r["kind"] == "P"  # PUT -> P, decimal-dollar strike
    assert r["close"] == 0.20 and r["volume"] == 37
    assert r["bid"] == 0.18 and r["ask"] == 0.22


def test_normalize_thetadata_v3_call_and_mid_fallback():
    # CALL -> C; close 0 (no trade) -> bid/ask mid
    df = _normalize_thetadata([_row(right="CALL", strike=6.0, close=0.0, bid=0.10, ask=0.20)])
    r = df.iloc[0]
    assert r["kind"] == "C"
    assert r["close"] == pytest.approx(0.15)
