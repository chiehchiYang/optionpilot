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
    return _yf_close(ticker.upper(), start, end)


def load_vix(start: str, end: str, symbol: str = "^VIX") -> pd.Series:
    """CBOE VIX daily close as a Series indexed by python date (the equity 'fear gauge').

    symbol='^VIX' (30-day) by default; pass '^VIX3M' for the 3-month for term-structure work."""
    return _yf_close(symbol, start, end)


def _yf_close(symbol: str, start: str, end: str) -> pd.Series:
    import yfinance as yf

    df = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=False)
    if df.empty:
        raise ValueError(f"no price data for {symbol} {start}..{end}")
    s = df["Close"].squeeze()
    s.index = [d.date() for d in s.index]
    return s


def load_ohlcv(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Daily OHLCV for a ticker (via yfinance), indexed by python date. Columns:
    open/high/low/close/volume. Powers the technical & sentiment dimensions of the screener."""
    import yfinance as yf

    df = yf.download(ticker.upper(), start=start, end=end, progress=False, auto_adjust=False)
    if df.empty:
        raise ValueError(f"no OHLCV for {ticker} {start}..{end}")
    out = pd.DataFrame({
        "open": df["Open"].squeeze().astype(float),
        "high": df["High"].squeeze().astype(float),
        "low": df["Low"].squeeze().astype(float),
        "close": df["Close"].squeeze().astype(float),
        "volume": df["Volume"].squeeze().astype(float),
    })
    out.index = [d.date() for d in out.index]
    return out


# screener metric name -> yfinance .info key (fundamental + valuation + context)
_FUND_KEYS = {
    "revenue_growth": "revenueGrowth", "earnings_growth": "earningsGrowth",
    "profit_margin": "profitMargins", "roe": "returnOnEquity", "debt_to_equity": "debtToEquity",
    "trailing_pe": "trailingPE", "forward_pe": "forwardPE",
    "price_to_sales": "priceToSalesTrailing12Months", "ev_ebitda": "enterpriseToEbitda",
}


def load_fundamentals(ticker: str) -> dict:
    """Fundamental + valuation fields from yfinance's .info (best-effort; keys may be missing for
    some names). Numeric where available; also returns sector and market_cap for context."""
    import yfinance as yf

    info = yf.Ticker(ticker.upper()).info or {}
    out: dict = {}
    for name, src in _FUND_KEYS.items():
        v = info.get(src)
        out[name] = float(v) if isinstance(v, (int, float)) else None
    peg = info.get("trailingPegRatio", info.get("pegRatio"))
    out["peg"] = float(peg) if isinstance(peg, (int, float)) else None
    out["sector"] = info.get("sector")
    mc = info.get("marketCap")
    out["market_cap"] = float(mc) if isinstance(mc, (int, float)) else None
    return out
