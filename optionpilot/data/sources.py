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

import hashlib
import json
from abc import ABC, abstractmethod
from datetime import date, timedelta

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
    def fetch_chain(self, ticker: str, start: str, end: str, approve=None) -> pd.DataFrame:
        """Return daily option-chain bars for `ticker` in the normalized schema.

        `approve(message, usd) -> bool` is consulted only when a paid download is needed
        (free sources / cache hits never call it)."""

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

    def fetch_chain(self, ticker: str, start: str, end: str, approve=None) -> pd.DataFrame:
        raw = self.fetcher.fetch(symbols=[self._parent(ticker)], schema="ohlcv-1d",
                                 start=start, end=end, stype_in="parent", approve=approve)
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


class ThetaDataSource(OptionDataSource):
    """ThetaData free tier — local Theta Terminal v3, EOD options with bid/ask + volume.

    Free and local, so there is no per-call cost (the spend-approval callback is not used).
    Requires a (free) ThetaData account + the v3 Theta Terminal running locally on port 25503;
    see docs/thetadata_setup.md. Verified: free tier serves multi-year history with bid/ask +
    volume, and each bar's `created` timestamp is its trading day.
    """

    name = "thetadata"

    def __init__(self, config: Config):
        self.config = config
        self.base = config.thetadata_url.rstrip("/")
        self.cache_dir = config.cache_dir / "thetadata"

    def fetch_chain(self, ticker: str, start: str, end: str, approve=None) -> pd.DataFrame:
        import requests

        key = hashlib.sha1(f"{ticker.upper()}|{start}|{end}".encode()).hexdigest()[:16]
        path = self.cache_dir / f"{key}.parquet"
        if path.exists():  # free + local, but slow (1 concurrent) — cache so tools reuse it
            return _ensure_date_cols(pd.read_parquet(path))

        import time

        from optionpilot.progress import report

        url = f"{self.base}/v3/option/history/eod"
        chunks = list(_date_chunks(start, end, max_days=365))  # v3 caps a request at 365 days
        report(f"ThetaData 抓取 {ticker.upper()} {start}~{end}:{len(chunks)} 個區塊"
               "(免費版單線,長區間可能數分鐘)…")
        rows: list[dict] = []
        t0 = time.monotonic()
        for i, (s, e) in enumerate(chunks, 1):  # noqa: E741 - e is a date string here
            params = {"symbol": ticker.upper(), "expiration": "*",
                      "start_date": s, "end_date": e, "format": "ndjson"}
            c0 = last = time.monotonic()
            with requests.get(url, params=params, timeout=300, stream=True) as r:
                r.raise_for_status()
                for line in r.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    rows.append(json.loads(line))
                    now = time.monotonic()
                    if now - last >= 2.0:  # heartbeat: still alive + throughput
                        report(f"區塊 {i}/{len(chunks)}:已收到 {len(rows):,} 筆"
                               f"(本區塊 {now - c0:.0f}s)…")
                        last = now
            elapsed = time.monotonic() - t0
            if i < len(chunks):  # ETA from the observed per-chunk pace
                eta = elapsed * (len(chunks) - i) / i
                report(f"區塊 {i}/{len(chunks)} 完成,已 {elapsed:.0f}s,預估剩餘 ~{eta:.0f}s"
                       f"(共 {len(rows):,} 筆)")
            else:
                report(f"抓取完成:{len(rows):,} 筆,耗時 {elapsed:.0f}s(整理中…)")
        df = _normalize_thetadata(rows)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path)
        return df


def _ensure_date_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Parquet may round-trip date columns to datetime64; coerce back to python date."""
    for col in ("date", "expiry"):
        if col in df.columns and len(df) and not isinstance(df[col].iloc[0], date):
            df[col] = pd.to_datetime(df[col]).dt.date
    return df


def _date_chunks(start: str, end: str, max_days: int = 365):
    """Split [start, end] into consecutive windows of at most `max_days` days each."""
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    cur = s
    while cur <= e:
        nxt = min(cur + timedelta(days=max_days - 1), e)
        yield cur.isoformat(), nxt.isoformat()
        cur = nxt + timedelta(days=1)


def _iso_date(s) -> date:
    return date.fromisoformat(str(s)[:10])


def _normalize_thetadata(rows: list[dict]) -> pd.DataFrame:
    """Map ThetaData v3 option EOD ndjson rows into the normalized schema.

    Strikes are decimal dollars; `right` is CALL/PUT; the bar date is the `created` timestamp's
    day (verified to equal the trading day, even for history). The daily mark is `close`,
    falling back to bid/ask mid when the contract did not trade (close == 0).
    """
    recs = []
    for d in rows:
        bid, ask = d.get("bid"), d.get("ask")
        close = d.get("close")
        if (not close) and bid is not None and ask is not None:
            close = (bid + ask) / 2.0
        kind = "C" if str(d.get("right", "")).upper().startswith("C") else "P"
        strike = float(d.get("strike"))
        recs.append({
            "date": _iso_date(d.get("created")),
            "contract": f"{d.get('symbol')}|{d.get('expiration')}|{kind}|{strike}",
            "expiry": _iso_date(d.get("expiration")),
            "strike": strike,
            "kind": kind,
            "close": close,
            "volume": d.get("volume"),
            "bid": bid,
            "ask": ask,
            "delta": np.nan,
            "iv": np.nan,
        })
    return pd.DataFrame(recs, columns=NORMALIZED_COLUMNS)


_SOURCES = {"databento": DatabentoSource, "thetadata": ThetaDataSource}


def get_source(config: Config, name: str | None = None) -> OptionDataSource:
    """Factory: build a data source by name (defaults to config.data_source)."""
    key = (name or config.data_source).lower()
    if key not in _SOURCES:
        raise ValueError(f"unknown data source: {key!r}. available: {list(_SOURCES)}")
    return _SOURCES[key](config)
