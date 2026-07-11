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

import contextlib
import json
import os
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
        """Range-aware INCREMENTAL cache, shared across users (one parquet per ticker holding ALL
        fetched dates). Only the dates not already cached are fetched, so overlapping/sub ranges
        reuse prior fetches instead of re-pulling the whole (slow) span."""
        from optionpilot.progress import report

        tk = _safe_ticker(ticker)
        s, e = date.fromisoformat(start), date.fromisoformat(end)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        tpath = self.cache_dir / f"{tk}.parquet"          # every bar we've fetched for this ticker
        cpath = self.cache_dir / f"{tk}.coverage.json"    # which date ranges we already hold

        with _cache_lock(self.cache_dir / f"{tk}.lock"):  # cross-process: no clobber on same ticker
            covered = _load_coverage(cpath)
            gaps = _subtract(covered, s, e)
            if gaps:
                report(f"ThetaData {tk} {start}~{end}:需補 {len(gaps)} 段缺口"
                       "(其餘用共用快取)…")
                existing = _ensure_date_cols(pd.read_parquet(tpath)) if tpath.exists() else None
                fresh: list[dict] = []
                for gi, (gs, ge) in enumerate(gaps, 1):
                    fresh.extend(self._fetch_range(tk, gs, ge, gi, len(gaps)))
                merged = _dedup_concat(existing, _normalize_thetadata(fresh))
                _atomic_write_parquet(merged, tpath)
                _save_coverage(cpath, covered + [(s, e)])
            else:
                report(f"ThetaData {tk} {start}~{end}:完全命中共用快取,不需抓取。")

        df = _ensure_date_cols(pd.read_parquet(tpath))
        return df[(df["date"] >= s) & (df["date"] <= e)].reset_index(drop=True)

    def _fetch_range(self, tk: str, s: date, e: date, gap_i: int, gap_n: int) -> list[dict]:
        """Fetch one missing [s, e] sub-range (chunked <=365d, streamed with live progress)."""
        import time

        import requests

        from optionpilot.progress import report
        url = f"{self.base}/v3/option/history/eod"
        rows: list[dict] = []
        t0 = time.monotonic()
        for cs, ce in _date_chunks(s.isoformat(), e.isoformat(), max_days=365):
            params = {"symbol": tk, "expiration": "*",
                      "start_date": cs, "end_date": ce, "format": "ndjson"}
            last = time.monotonic()
            with requests.get(url, params=params, timeout=300, stream=True) as r:
                r.raise_for_status()
                for line in r.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    rows.append(json.loads(line))
                    now = time.monotonic()
                    if now - last >= 2.0:  # heartbeat: alive + throughput
                        report(f"缺口 {gap_i}/{gap_n} {s}~{e}:已收到 {len(rows):,} 筆"
                               f"(已 {now - t0:.0f}s)…")
                        last = now
        report(f"缺口 {gap_i}/{gap_n} {s}~{e} 完成:{len(rows):,} 筆"
               f"(耗時 {time.monotonic() - t0:.0f}s)")
        return rows


# ---- range-aware incremental cache helpers (shared per-ticker parquet + coverage) ----

def _safe_ticker(ticker: str) -> str:
    import re
    return re.sub(r"[^A-Z0-9._-]", "_", ticker.upper()) or "UNKNOWN"


def _merge_intervals(intervals: list[tuple[date, date]]) -> list[tuple[date, date]]:
    """Sort + merge overlapping OR adjacent (touching) date intervals."""
    out: list[tuple[date, date]] = []
    for s, e in sorted((s, e) for s, e in intervals if s <= e):
        if out and s <= out[-1][1] + timedelta(days=1):
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def _subtract(covered: list[tuple[date, date]], s: date, e: date) -> list[tuple[date, date]]:
    """The parts of [s, e] NOT already covered — i.e. the date ranges we still need to fetch."""
    gaps: list[tuple[date, date]] = []
    cur = s
    for cs, ce in _merge_intervals(covered):
        if ce < cur or cs > e:
            continue
        if cs > cur:
            gaps.append((cur, min(cs - timedelta(days=1), e)))
        cur = max(cur, ce + timedelta(days=1))
        if cur > e:
            break
    if cur <= e:
        gaps.append((cur, e))
    return [(a, b) for a, b in gaps if a <= b]


def _load_coverage(path) -> list[tuple[date, date]]:
    try:
        if not path.exists():
            return []
        return [(date.fromisoformat(a), date.fromisoformat(b))
                for a, b in json.loads(path.read_text(encoding="utf-8"))]
    except Exception:  # noqa: BLE001 - a corrupt/absent coverage file just means re-fetch
        return []


def _save_coverage(path, intervals: list[tuple[date, date]]) -> None:
    data = [[a.isoformat(), b.isoformat()] for a, b in _merge_intervals(intervals)]
    _atomic_write_text(path, json.dumps(data))


def _dedup_concat(existing, new_df):
    df = new_df if existing is None else pd.concat([existing, new_df], ignore_index=True)
    return df.drop_duplicates(subset=["date", "contract"], keep="last").reset_index(drop=True)


def _atomic_write_parquet(df, path) -> None:
    tmp = path.with_name(path.name + ".tmp")
    df.to_parquet(tmp)
    os.replace(tmp, path)


def _atomic_write_text(path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


@contextlib.contextmanager
def _cache_lock(lockpath):
    """Cross-process exclusive lock so concurrent fetches of the same ticker don't clobber cache."""
    try:
        import fcntl
    except ImportError:  # non-Unix -> best-effort, no lock
        yield
        return
    lockpath.parent.mkdir(parents=True, exist_ok=True)
    f = open(lockpath, "w")
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        finally:
            f.close()


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
