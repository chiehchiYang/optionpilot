"""Tests for the range-aware incremental ThetaData cache (interval math + only-fetch-gaps)."""

from datetime import date

from optionpilot.config import Config
from optionpilot.data.sources import (
    ThetaDataSource,
    _dedup_concat,
    _load_coverage,
    _merge_intervals,
    _save_coverage,
    _subtract,
)


def _d(s):
    return date.fromisoformat(s)


def test_merge_overlapping_and_adjacent():
    merged = _merge_intervals([(_d("2024-01-01"), _d("2024-03-31")),
                               (_d("2024-04-01"), _d("2024-06-30")),   # adjacent -> merge
                               (_d("2024-06-15"), _d("2024-08-31"))])  # overlaps -> merge
    assert merged == [(_d("2024-01-01"), _d("2024-08-31"))]


def test_subtract_finds_only_the_gaps():
    covered = [(_d("2024-03-01"), _d("2024-09-30"))]
    assert _subtract(covered, _d("2024-01-01"), _d("2024-12-31")) == [
        (_d("2024-01-01"), _d("2024-02-29")), (_d("2024-10-01"), _d("2024-12-31"))]


def test_subtract_fully_covered_is_empty():
    covered = [(_d("2024-01-01"), _d("2024-12-31"))]
    assert _subtract(covered, _d("2024-03-01"), _d("2024-06-30")) == []


def test_subtract_nothing_covered_is_the_whole_range():
    assert _subtract([], _d("2024-01-01"), _d("2024-06-30")) == [
        (_d("2024-01-01"), _d("2024-06-30"))]


def test_coverage_roundtrip(tmp_path):
    p = tmp_path / "ZETA.coverage.json"
    ivs = [(_d("2024-01-01"), _d("2024-03-31")), (_d("2024-04-01"), _d("2024-06-30"))]
    _save_coverage(p, ivs)
    assert _load_coverage(p) == [(_d("2024-01-01"), _d("2024-06-30"))]   # saved merged


def _row(tk, d):
    return {"created": f"{d}T00:00:00", "symbol": tk, "expiration": "2024-12-20",
            "right": "C", "strike": 100.0, "close": 1.0, "volume": 5, "bid": 0.9, "ask": 1.1}


def test_incremental_fetch_only_pulls_missing_gaps(tmp_path, monkeypatch):
    cfg = Config(**{**Config.load(dotenv=False).__dict__, "cache_dir": tmp_path})
    src = ThetaDataSource(cfg)
    calls = []

    def fake_fetch_range(tk, s, e, gap_i, gap_n):
        calls.append((str(s), str(e)))
        return [_row(tk, s), _row(tk, e)]

    monkeypatch.setattr(src, "_fetch_range", fake_fetch_range)

    src.fetch_chain("ZETA", "2024-01-01", "2024-06-30")      # first: full range
    src.fetch_chain("ZETA", "2024-03-01", "2024-09-30")      # only the 07-01..09-30 gap
    df = src.fetch_chain("ZETA", "2024-02-01", "2024-05-31")  # fully covered -> no fetch

    assert calls == [("2024-01-01", "2024-06-30"), ("2024-07-01", "2024-09-30")]
    assert (df["date"] >= _d("2024-02-01")).all() and (df["date"] <= _d("2024-05-31")).all()


def test_dedup_concat_drops_duplicate_bars():
    import pandas as pd
    a = pd.DataFrame({"date": [_d("2024-01-02")], "contract": ["X"], "close": [1.0]})
    b = pd.DataFrame({"date": [_d("2024-01-02"), _d("2024-01-03")],
                      "contract": ["X", "Y"], "close": [1.5, 2.0]})
    out = _dedup_concat(a, b)
    assert len(out) == 2 and out[out["contract"] == "X"]["close"].iloc[0] == 1.5  # keep last
