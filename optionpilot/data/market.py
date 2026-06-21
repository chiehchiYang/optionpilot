"""Convenience loaders the agent tools use: option chain (via a DataSource) + underlying.

Keeps tools thin: each takes a ticker + dates and gets a normalized option chain from the
configured/selected DataSource, and underlying closes from yfinance.
"""

from __future__ import annotations

import pandas as pd

from optionpilot.config import Config
from optionpilot.data.sources import get_source


def load_option_chain(
    config: Config, ticker: str, start: str, end: str, source: str | None = None, approve=None
) -> pd.DataFrame:
    """Load normalized daily option-chain bars for a ticker from the chosen DataSource.

    `approve(message, usd) -> bool` is consulted only if a paid download is needed."""
    return get_source(config, source).fetch_chain(ticker, start, end, approve=approve)


def load_underlying(ticker: str, start: str, end: str) -> pd.Series:
    """Underlying daily close as a Series indexed by python date (via yfinance)."""
    import yfinance as yf

    df = yf.download(ticker.upper(), start=start, end=end, progress=False, auto_adjust=False)
    if df.empty:
        raise ValueError(f"no underlying price data for {ticker} {start}..{end}")
    s = df["Close"].squeeze()
    s.index = [d.date() for d in s.index]
    return s
