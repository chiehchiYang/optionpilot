"""Unusual options activity + put/call flow from a normalized option chain.

Input is the normalized schema (see data.sources): columns `date`, `contract`, `kind`,
`volume`. These are Stockwe-style flow signals — screening aids, not standalone trade
signals (validate by backtest before trading them). Sources without `volume` (e.g. DoltHub)
yield no flags.
"""

from __future__ import annotations

import pandas as pd


def unusual_volume(
    df: pd.DataFrame,
    lookback: int = 20,
    ratio_threshold: float = 3.0,
    min_volume: int = 50,
) -> pd.DataFrame:
    """Flag (contract, day) rows whose volume far exceeds the contract's recent average.

    ratio = today's volume / trailing `lookback`-day mean volume of the SAME contract
    (current day excluded). Rows with ratio >= ratio_threshold and volume >= min_volume are
    returned, sorted by ratio descending. Returns empty if `volume` is absent/all-NaN.
    """
    if "volume" not in df.columns or df["volume"].notna().sum() == 0:
        return pd.DataFrame(columns=["date", "contract", "volume", "avg_volume", "ratio"])
    d = df.dropna(subset=["volume"]).sort_values(["contract", "date"])
    avg = d.groupby("contract")["volume"].transform(
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
        flagged[["date", "contract", "volume", "avg_volume", "ratio"]]
        .sort_values("ratio", ascending=False)
        .reset_index(drop=True)
    )


def daily_put_call_ratio(df: pd.DataFrame) -> pd.DataFrame:
    """Daily put/call VOLUME ratio (>1 = more put volume). Needs `volume` + `kind`."""
    d = df.dropna(subset=["volume"]) if "volume" in df.columns else df.iloc[0:0]
    piv = (
        d.groupby(["date", "kind"])["volume"].sum().unstack(fill_value=0)
        .rename(columns={"P": "put_volume", "C": "call_volume"})
    )
    for col in ("put_volume", "call_volume"):
        if col not in piv.columns:
            piv[col] = 0
    piv["put_call_ratio"] = piv["put_volume"] / piv["call_volume"].replace(0, pd.NA)
    return piv[["put_volume", "call_volume", "put_call_ratio"]]
