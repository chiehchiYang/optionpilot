"""Binance USDⓈ-M (U 本位 / USDT-margined) perpetual-futures PUBLIC market data.

No API key, no signing, read-only — these are the public futures REST endpoints on
``https://fapi.binance.com``. This is the crypto analog of our options data layer: instead
of option chains we pull klines (OHLCV), funding-rate history, open interest, and the
long/short account ratio — the inputs for funding-carry, momentum, and risk analysis.

Everything returns a tidy pandas DataFrame indexed/sorted by time (UTC). ``requests`` is an
optional ``data`` extra, imported lazily so importing this module never hard-fails.
"""

from __future__ import annotations

import pandas as pd

FAPI = "https://fapi.binance.com"
_TIMEOUT = 20


def _get(path: str, params: dict | None = None, base: str = FAPI) -> object:
    """GET a public Binance endpoint and return parsed JSON (list or dict)."""
    try:
        import requests
    except ImportError as e:  # pragma: no cover - clear message if extra missing
        raise RuntimeError("binance data needs the 'data' extra: pip install -e '.[data]'") from e
    r = requests.get(f"{base}{path}", params=params or {}, timeout=_TIMEOUT)
    if r.status_code != 200:
        raise RuntimeError(f"Binance {path} -> HTTP {r.status_code}: {r.text[:200]}")
    return r.json()


def _ms(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series.astype("int64"), unit="ms", utc=True)


def klines(symbol: str, interval: str = "1h", limit: int = 500) -> pd.DataFrame:
    """OHLCV candles. interval e.g. '1m','5m','15m','1h','4h','1d'. limit<=1500.

    Returns columns open/high/low/close/volume/quote_volume/trades/taker_buy_base,
    indexed by open_time (UTC), oldest->newest.
    """
    raw = _get("/fapi/v1/klines", {"symbol": symbol.upper(), "interval": interval,
                                   "limit": min(int(limit), 1500)})
    if not raw:
        return pd.DataFrame()
    cols = ["open_time", "open", "high", "low", "close", "volume", "close_time",
            "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore"]
    df = pd.DataFrame(raw, columns=cols)
    out = pd.DataFrame({
        "open": df["open"].astype(float),
        "high": df["high"].astype(float),
        "low": df["low"].astype(float),
        "close": df["close"].astype(float),
        "volume": df["volume"].astype(float),
        "quote_volume": df["quote_volume"].astype(float),
        "trades": df["trades"].astype("int64"),
        "taker_buy_base": df["taker_buy_base"].astype(float),
    })
    out.index = _ms(df["open_time"])
    out.index.name = "open_time"
    return out.sort_index()


def funding_rate_history(symbol: str, limit: int = 1000) -> pd.DataFrame:
    """Historical funding rates (the per-interval rate longs pay shorts when positive).

    Returns columns funding_time (UTC) and funding_rate (decimal, e.g. 0.0001 = 0.01%),
    oldest->newest. limit<=1000.
    """
    raw = _get("/fapi/v1/fundingRate", {"symbol": symbol.upper(), "limit": min(int(limit), 1000)})
    if not raw:
        return pd.DataFrame(columns=["funding_time", "funding_rate"])
    df = pd.DataFrame(raw)
    out = pd.DataFrame({
        "funding_time": _ms(df["fundingTime"]),
        "funding_rate": df["fundingRate"].astype(float),
    })
    return out.sort_values("funding_time").reset_index(drop=True)


def mark_price(symbol: str) -> dict:
    """Current mark/index price + the last & next funding (premiumIndex endpoint)."""
    d = _get("/fapi/v1/premiumIndex", {"symbol": symbol.upper()})
    return {
        "symbol": d["symbol"],
        "mark_price": float(d["markPrice"]),
        "index_price": float(d["indexPrice"]),
        "last_funding_rate": float(d["lastFundingRate"]),
        "next_funding_time": pd.to_datetime(int(d["nextFundingTime"]), unit="ms", utc=True),
    }


def open_interest_hist(symbol: str, period: str = "1h", limit: int = 500) -> pd.DataFrame:
    """Open-interest history (contracts + USD value). period e.g. '5m','1h','4h','1d'.

    Returns columns time (UTC), open_interest (base units), open_interest_usd. limit<=500.
    NOTE: Binance only serves the most recent ~30 days for this stats endpoint.
    """
    raw = _get("/futures/data/openInterestHist",
               {"symbol": symbol.upper(), "period": period, "limit": min(int(limit), 500)})
    if not raw:
        return pd.DataFrame(columns=["time", "open_interest", "open_interest_usd"])
    df = pd.DataFrame(raw)
    out = pd.DataFrame({
        "time": _ms(df["timestamp"]),
        "open_interest": df["sumOpenInterest"].astype(float),
        "open_interest_usd": df["sumOpenInterestValue"].astype(float),
    })
    return out.sort_values("time").reset_index(drop=True)


def long_short_ratio(symbol: str, period: str = "1h", limit: int = 500) -> pd.DataFrame:
    """Global long/short ACCOUNT ratio (crowd positioning). limit<=500, ~30 days only.

    Returns columns time (UTC), long_short_ratio, long_account, short_account (fractions).
    """
    raw = _get("/futures/data/globalLongShortAccountRatio",
               {"symbol": symbol.upper(), "period": period, "limit": min(int(limit), 500)})
    if not raw:
        return pd.DataFrame(columns=["time", "long_short_ratio", "long_account", "short_account"])
    df = pd.DataFrame(raw)
    out = pd.DataFrame({
        "time": _ms(df["timestamp"]),
        "long_short_ratio": df["longShortRatio"].astype(float),
        "long_account": df["longAccount"].astype(float),
        "short_account": df["shortAccount"].astype(float),
    })
    return out.sort_values("time").reset_index(drop=True)
