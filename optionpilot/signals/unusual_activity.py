"""Unusual options activity + put/call flow — from per-contract daily OHLCV bars.

Input is the Databento OPRA-style frame: a datetime index (or `date`/`ts_event` column),
plus `symbol` (OSI) and `volume` columns. These are the Stockwe-style flow signals; they are
screening aids, not standalone trade signals (validate by backtest before trading them).
"""

from __future__ import annotations

import pandas as pd

from optionpilot.data.osi import try_parse_osi


def _with_date(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with a plain `date` column (from a date column or the datetime index)."""
    out = df.reset_index()
    if "date" not in out.columns:
        tcol = next((c for c in ("ts_event", "ts_recv", "index") if c in out.columns), out.columns[0])
        out["date"] = pd.to_datetime(out[tcol]).dt.date
    return out


def unusual_volume(
    df: pd.DataFrame,
    lookback: int = 20,
    ratio_threshold: float = 3.0,
    min_volume: int = 50,
) -> pd.DataFrame:
    """Flag (contract, day) rows whose volume far exceeds the contract's recent average.

    ratio = today's volume / trailing `lookback`-day mean volume of the SAME contract
    (the current day is excluded from the average). Rows with ratio >= ratio_threshold and
    volume >= min_volume are returned, sorted by ratio descending.
    """
    d = _with_date(df).sort_values(["symbol", "date"])
    avg = d.groupby("symbol")["volume"].transform(
        lambda s: s.shift(1).rolling(lookback, min_periods=5).mean()
    )
    d = d.assign(avg_volume=avg)
    d["ratio"] = d["volume"] / d["avg_volume"]
    flagged = d[
        (d["volume"] >= min_volume)
        & (d["avg_volume"].notna())
        & (d["ratio"] >= ratio_threshold)
    ]
    return (
        flagged[["date", "symbol", "volume", "avg_volume", "ratio"]]
        .sort_values("ratio", ascending=False)
        .reset_index(drop=True)
    )


def daily_put_call_ratio(df: pd.DataFrame) -> pd.DataFrame:
    """Daily put/call VOLUME ratio (a crude sentiment gauge; >1 = more put volume).

    Returns a frame indexed by date with columns put_volume, call_volume, put_call_ratio.
    """
    d = _with_date(df)
    parsed = d["symbol"].map(try_parse_osi)
    d = d.assign(kind=parsed.map(lambda c: c.kind if c else None)).dropna(subset=["kind"])
    piv = (
        d.groupby(["date", "kind"])["volume"].sum().unstack(fill_value=0)
        .rename(columns={"P": "put_volume", "C": "call_volume"})
    )
    for col in ("put_volume", "call_volume"):
        if col not in piv.columns:
            piv[col] = 0
    piv["put_call_ratio"] = piv["put_volume"] / piv["call_volume"].replace(0, pd.NA)
    return piv[["put_volume", "call_volume", "put_call_ratio"]]
