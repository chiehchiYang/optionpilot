"""Tests for DatabentoFetcher's cost-guard + cache logic.

The databento SDK calls (_get_cost / _download) are replaced with fakes, so these run with
no API key and no network — they exercise our guard/cache decisions, not Databento itself.
"""

import pandas as pd
import pytest

from optionpilot.config import Config
from optionpilot.data.databento_fetcher import (
    CostEstimate,
    CostGuardError,
    DatabentoFetcher,
)

ARGS = dict(symbols=["SPY"], schema="ohlcv-1m", start="2024-01-02", end="2024-01-03")


def _fetcher(tmp_path, max_usd=5.0) -> DatabentoFetcher:
    cfg = Config(cache_dir=tmp_path, max_fetch_usd=max_usd, databento_api_key="fake")
    return DatabentoFetcher(cfg)


def _fake_df() -> pd.DataFrame:
    return pd.DataFrame({"close": [1.0, 2.0], "volume": [10, 20]})


def test_guard_blocks_expensive_fetch_without_downloading(tmp_path):
    f = _fetcher(tmp_path, max_usd=1.0)
    f._get_cost = lambda *a, **k: CostEstimate(usd=10.0)

    def _no_download(*a, **k):
        raise AssertionError("download must not run when guard trips")

    f._download = _no_download
    with pytest.raises(CostGuardError) as exc:
        f.fetch(**ARGS)
    assert exc.value.estimate.usd == 10.0
    assert exc.value.limit == 1.0
    # nothing cached
    assert not any(tmp_path.rglob("*.parquet"))


def test_fetch_under_budget_downloads_and_caches(tmp_path):
    f = _fetcher(tmp_path, max_usd=5.0)
    f._get_cost = lambda *a, **k: CostEstimate(usd=0.5)
    f._download = lambda *a, **k: _fake_df()

    df = f.fetch(**ARGS)
    pd.testing.assert_frame_equal(df, _fake_df())
    assert len(list(tmp_path.rglob("*.parquet"))) == 1


def test_cache_hit_skips_estimate_and_download(tmp_path):
    f = _fetcher(tmp_path)
    f._get_cost = lambda *a, **k: CostEstimate(usd=0.5)
    f._download = lambda *a, **k: _fake_df()
    f.fetch(**ARGS)  # populate cache

    # second call: both seams now blow up; cache must satisfy the request
    f._get_cost = lambda *a, **k: (_ for _ in ()).throw(AssertionError("should be cached"))
    f._download = lambda *a, **k: (_ for _ in ()).throw(AssertionError("should be cached"))
    df = f.fetch(**ARGS)
    pd.testing.assert_frame_equal(df, _fake_df())


def test_override_guard_allows_expensive_fetch(tmp_path):
    f = _fetcher(tmp_path, max_usd=1.0)
    f._get_cost = lambda *a, **k: CostEstimate(usd=10.0)
    f._download = lambda *a, **k: _fake_df()
    df = f.fetch(**ARGS, override_guard=True)
    assert len(df) == 2


def test_force_bypasses_cache(tmp_path):
    f = _fetcher(tmp_path)
    f._get_cost = lambda *a, **k: CostEstimate(usd=0.1)
    calls = {"n": 0}

    def _dl(*a, **k):
        calls["n"] += 1
        return _fake_df()

    f._download = _dl
    f.fetch(**ARGS)
    f.fetch(**ARGS, force=True)
    assert calls["n"] == 2  # forced re-download


def test_cache_key_differs_by_params(tmp_path):
    f = _fetcher(tmp_path)
    k1 = f._cache_key(["SPY"], "ohlcv-1m", "2024-01-02", "2024-01-03", "parent")
    k2 = f._cache_key(["SPY"], "trades", "2024-01-02", "2024-01-03", "parent")
    k3 = f._cache_key(["QQQ"], "ohlcv-1m", "2024-01-02", "2024-01-03", "parent")
    assert k1 != k2 != k3 and k1 != k3


def test_missing_args_raises(tmp_path):
    f = _fetcher(tmp_path)
    with pytest.raises(ValueError):
        f.fetch(symbols=[], schema="ohlcv-1m", start="2024-01-02", end="2024-01-03")
