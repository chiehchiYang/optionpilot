"""DatabentoFetcher: historical OPRA pulls with a cost guard and Parquet cache.

This is the most dangerous part of the project: OPRA is enormous (1.6M+ symbols) and pulls
are billed per GB against the $125 free credit. Every fetch therefore:
  1. estimates its byte size / cost via Databento's metadata API BEFORE downloading,
  2. aborts (or requests approval) if the estimate exceeds Config.max_fetch_usd,
  3. caches the result to Parquet keyed by (dataset, symbols, schema, start, end).

Implementation lands next. The interface below is what the fetch_options_data tool calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from optionpilot.config import Config


@dataclass
class CostEstimate:
    n_bytes: int
    usd: float
    record_count: int | None = None


class CostGuardError(RuntimeError):
    """Raised when an estimated fetch exceeds the configured budget."""


class DatabentoFetcher:
    DATASET = "OPRA.PILLAR"

    def __init__(self, config: Config):
        self.config = config
        self.cache_dir: Path = config.cache_dir / "databento"

    def estimate_cost(
        self, symbols: list[str], schema: str, start: str, end: str
    ) -> CostEstimate:
        """Call Databento's metadata.get_cost / get_record_count before downloading.

        TODO: implement via databento.Historical().metadata.get_cost(...).
        """
        raise NotImplementedError("DatabentoFetcher.estimate_cost")

    def fetch(
        self,
        symbols: list[str],
        schema: str = "ohlcv-1m",
        start: str = "",
        end: str = "",
        force: bool = False,
    ):
        """Fetch (cache-aware) after passing the cost guard. Returns a DataFrame.

        Flow: cache hit? -> return. else estimate_cost -> guard -> download -> cache -> return.
        TODO: implement download via databento.Historical().timeseries.get_range(...).
        """
        raise NotImplementedError("DatabentoFetcher.fetch")
