"""Convenience loaders that the agent tools use: option chain + underlying price series.

Keeps the tools thin and self-contained — each tool takes a ticker + dates and loads what it
needs (cached option chain via Databento, underlying closes via yfinance).
"""

from __future__ import annotations

import pandas as pd

from optionpilot.config import Config
from optionpilot.data.databento_fetcher import DatabentoFetcher


def load_option_chain(
    config: Config, ticker: str, start: str, end: str, schema: str = "ohlcv-1d"
) -> pd.DataFrame:
    """Load the daily option-chain bars for a ticker (cache-aware, cost-guarded)."""
    parent = ticker if ticker.endswith(".OPT") else f"{ticker.upper()}.OPT"
    return DatabentoFetcher(config).fetch(
        symbols=[parent], schema=schema, start=start, end=end, stype_in="parent"
    )


def load_underlying(ticker: str, start: str, end: str) -> pd.Series:
    """Underlying daily close as a Series indexed by python date (via yfinance)."""
    import yfinance as yf

    df = yf.download(ticker.upper(), start=start, end=end, progress=False, auto_adjust=False)
    if df.empty:
        raise ValueError(f"no underlying price data for {ticker} {start}..{end}")
    s = df["Close"].squeeze()
    s.index = [d.date() for d in s.index]
    return s
