"""DatabentoFetcher: historical OPRA pulls with a cost guard and Parquet cache.

This is the most dangerous part of the project: OPRA is enormous (1.6M+ symbols) and pulls
are billed per GB against the $125 free credit. Every fetch therefore:
  1. estimates its cost via Databento's metadata API BEFORE downloading,
  2. raises CostGuardError if the estimate exceeds Config.max_fetch_usd (unless overridden),
  3. caches the result to Parquet keyed by (dataset, symbols, schema, start, end).

The actual databento SDK calls live in `_get_cost` / `_download`, imported lazily so the
rest of OptionPilot (and the test suite) doesn't require the `databento` package or network.
Tests monkeypatch those two seams to exercise the guard/cache logic.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from optionpilot.config import Config


@dataclass
class CostEstimate:
    usd: float
    n_bytes: int | None = None
    record_count: int | None = None


class CostGuardError(RuntimeError):
    """Raised when an estimated fetch exceeds the configured budget."""

    def __init__(self, estimate: CostEstimate, limit: float):
        self.estimate = estimate
        self.limit = limit
        super().__init__(
            f"Databento fetch estimated at ${estimate.usd:.4f} exceeds the "
            f"max_fetch_usd guard of ${limit:.2f}. Narrow the symbols/date range/schema, "
            f"or raise OPTIONPILOT_MAX_FETCH_USD if this is intended."
        )


class DatabentoFetcher:
    DATASET = "OPRA.PILLAR"

    def __init__(self, config: Config):
        self.config = config
        self.cache_dir: Path = config.cache_dir / "databento"

    # --- cache ---------------------------------------------------------------
    def _cache_key(self, symbols: list[str], schema: str, start: str, end: str,
                   stype_in: str) -> str:
        payload = json.dumps(
            {"dataset": self.DATASET, "symbols": sorted(symbols), "schema": schema,
             "start": start, "end": end, "stype_in": stype_in},
            sort_keys=True,
        )
        return hashlib.sha1(payload.encode()).hexdigest()[:16]

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.parquet"

    # --- databento SDK seams (monkeypatched in tests) ------------------------
    def _client(self):
        if not self.config.databento_api_key:
            raise RuntimeError(
                "DATABENTO_API_KEY is not set; cannot reach Databento. Set it in .env."
            )
        import databento as db  # lazy: optional dependency

        return db.Historical(self.config.databento_api_key)

    def _get_cost(self, symbols: list[str], schema: str, start: str, end: str,
                  stype_in: str) -> CostEstimate:
        client = self._client()
        usd = client.metadata.get_cost(
            dataset=self.DATASET, symbols=symbols, schema=schema,
            start=start, end=end, stype_in=stype_in,
        )
        try:
            count = client.metadata.get_record_count(
                dataset=self.DATASET, symbols=symbols, schema=schema,
                start=start, end=end, stype_in=stype_in,
            )
        except Exception:  # noqa: BLE001 - record count is best-effort
            count = None
        return CostEstimate(usd=float(usd), record_count=count)

    def _download(self, symbols: list[str], schema: str, start: str, end: str,
                  stype_in: str) -> pd.DataFrame:
        client = self._client()
        store = client.timeseries.get_range(
            dataset=self.DATASET, symbols=symbols, schema=schema,
            start=start, end=end, stype_in=stype_in,
        )
        return store.to_df()

    # --- public API ----------------------------------------------------------
    def estimate_cost(self, symbols: list[str], schema: str, start: str, end: str,
                      stype_in: str = "parent") -> CostEstimate:
        """Estimate cost before downloading. Does not enforce the guard."""
        return self._get_cost(symbols, schema, start, end, stype_in)

    def fetch(
        self,
        symbols: list[str],
        schema: str = "ohlcv-1m",
        start: str = "",
        end: str = "",
        stype_in: str = "parent",
        force: bool = False,
        override_guard: bool = False,
    ) -> pd.DataFrame:
        """Cache-aware fetch behind the cost guard.

        Flow: cache hit (unless force) -> return. Else estimate -> guard -> download ->
        cache -> return. Raises CostGuardError if the estimate exceeds the budget.
        """
        if not symbols or not start or not end:
            raise ValueError("symbols, start and end are required")

        key = self._cache_key(symbols, schema, start, end, stype_in)
        path = self._cache_path(key)
        if path.exists() and not force:
            return pd.read_parquet(path)

        estimate = self.estimate_cost(symbols, schema, start, end, stype_in)
        if not override_guard and estimate.usd > self.config.max_fetch_usd:
            raise CostGuardError(estimate, self.config.max_fetch_usd)

        df = self._download(symbols, schema, start, end, stype_in)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path)
        return df
