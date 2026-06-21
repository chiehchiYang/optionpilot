"""Pluggable option-chain data sources behind one normalized schema.

Consumers (backtests, signals) read the NORMALIZED frame below and never touch a provider's
native format — so a new source (DoltHub-local, ThetaData, ...) slots in without rewrites.

Normalized option-chain DataFrame columns:
    date     (datetime.date)  trading day of the bar
    contract (str)            stable per-contract id (e.g. the OSI symbol)
    expiry   (datetime.date)
    strike   (float)
    kind     ('C' | 'P')
    close    (float)          the mark price for the day
    volume   (float)          contracts traded that day; NaN if the source lacks it
    bid, ask (float)          NaN if unavailable
    delta, iv(float)          NaN if unavailable

A source need only populate what it has; missing columns are NaN and consumers degrade
gracefully (e.g. the unusual-volume signal needs `volume`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
import pandas as pd

from optionpilot.config import Config
from optionpilot.data.databento_fetcher import DatabentoFetcher
from optionpilot.data.osi import try_parse_osi

NORMALIZED_COLUMNS = [
    "date", "contract", "expiry", "strike", "kind",
    "close", "volume", "bid", "ask", "delta", "iv",
]


class OptionDataSource(ABC):
    name: str = "abstract"

    @abstractmethod
    def fetch_chain(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        """Return daily option-chain bars for `ticker` in the normalized schema."""

    def estimate_usd(self, ticker: str, start: str, end: str) -> float | None:
        """Estimated cost in USD, or None for free sources."""
        return None


class DatabentoSource(OptionDataSource):
    """Databento OPRA — any US ticker, OHLCV + volume (no bid/ask or greeks)."""

    name = "databento"

    def __init__(self, config: Config):
        self.config = config
        self.fetcher = DatabentoFetcher(config)

    @staticmethod
    def _parent(ticker: str) -> str:
        return ticker if ticker.endswith(".OPT") else f"{ticker.upper()}.OPT"

    def estimate_usd(self, ticker: str, start: str, end: str) -> float | None:
        return self.fetcher.estimate_cost(
            symbols=[self._parent(ticker)], schema="ohlcv-1d",
            start=start, end=end, stype_in="parent",
        ).usd

    def fetch_chain(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        raw = self.fetcher.fetch(symbols=[self._parent(ticker)], schema="ohlcv-1d",
                                 start=start, end=end, stype_in="parent")
        return _normalize_databento(raw)


def _normalize_databento(df: pd.DataFrame) -> pd.DataFrame:
    d = df.reset_index()
    tcol = next((c for c in ("ts_event", "ts_recv", "index") if c in d.columns), d.columns[0])
    dates = pd.to_datetime(d[tcol]).dt.date
    parsed = d["symbol"].map(try_parse_osi)
    mask = parsed.notna().to_numpy()
    d, parsed, dates = d[mask], parsed[mask], dates[mask]
    out = pd.DataFrame({
        "date": dates.to_numpy(),
        "contract": d["symbol"].str.strip().to_numpy(),
        "expiry": [c.expiry for c in parsed],
        "strike": [c.strike for c in parsed],
        "kind": [c.kind for c in parsed],
        "close": d["close"].to_numpy(),
        "volume": d["volume"].to_numpy(),
    })
    for col in ("bid", "ask", "delta", "iv"):
        out[col] = np.nan
    return out[NORMALIZED_COLUMNS]


_SOURCES = {"databento": DatabentoSource}


def get_source(config: Config, name: str | None = None) -> OptionDataSource:
    """Factory: build a data source by name (defaults to config.data_source)."""
    key = (name or config.data_source).lower()
    if key not in _SOURCES:
        raise ValueError(f"unknown data source: {key!r}. available: {list(_SOURCES)}")
    return _SOURCES[key](config)
