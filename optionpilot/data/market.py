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


def _map_info(info: dict) -> dict:
    """Map a yfinance .info dict to our snapshot metric names (numeric where present)."""
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


def load_fundamentals(ticker: str) -> dict:
    """Fundamental + valuation snapshot from yfinance's .info (best-effort; some keys may be
    missing). Numeric where available; also returns sector and market_cap for context."""
    import yfinance as yf

    return _map_info(yf.Ticker(ticker.upper()).info or {})


# quarterly income-statement line items -> the yfinance row names we accept (aliases vary)
_FIN_ROWS = {
    "revenue": ["Total Revenue", "TotalRevenue", "Operating Revenue"],
    "gross_profit": ["Gross Profit", "GrossProfit"],
    "operating_income": ["Operating Income", "OperatingIncome", "Total Operating Income As Reported"],
    "net_income": ["Net Income", "NetIncome", "Net Income Common Stockholders"],
    "diluted_eps": ["Diluted EPS", "DilutedEPS"],
}


def load_financials(ticker: str, quarters: int = 8) -> dict:
    """Recent quarterly income-statement lines + the current .info snapshot + next earnings date.

    Returns {"quarterly": [oldest..newest of {period, revenue, gross_profit, operating_income,
    net_income, diluted_eps}], "snapshot": <_map_info>, "next_earnings": iso|None}. Best-effort:
    yfinance shapes vary, so missing pieces degrade to None rather than raising."""
    import yfinance as yf

    t = yf.Ticker(ticker.upper())
    quarterly: list[dict] = []
    try:
        q = t.quarterly_income_stmt
    except Exception:  # noqa: BLE001
        q = None
    if q is not None and not q.empty:
        for col in list(q.columns)[: int(quarters)]:   # yfinance gives newest-first
            row = {"period": col.date().isoformat() if hasattr(col, "date") else str(col)}
            for name, aliases in _FIN_ROWS.items():
                val = None
                for a in aliases:
                    if a in q.index:
                        v = q.loc[a, col]
                        if v == v:   # not NaN
                            val = float(v)
                            break
                row[name] = val
            quarterly.append(row)
        quarterly.reverse()   # oldest -> newest

    try:
        snapshot = _map_info(t.info or {})
    except Exception:  # noqa: BLE001
        snapshot = {}

    next_earnings = None
    try:
        cal = t.calendar
        ed = cal.get("Earnings Date") if isinstance(cal, dict) else None
        if isinstance(ed, (list, tuple)) and ed:
            next_earnings = str(ed[0])
        elif ed:
            next_earnings = str(ed)
    except Exception:  # noqa: BLE001
        next_earnings = None

    return {"quarterly": quarterly, "snapshot": snapshot, "next_earnings": next_earnings}
