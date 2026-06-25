"""Tests for the fundamentals summary (pure logic, no network)."""

from optionpilot.fundamentals import summarize_fundamentals


def _q(period, rev, gp, oi, ni, eps):
    return {"period": period, "revenue": rev, "gross_profit": gp, "operating_income": oi,
            "net_income": ni, "diluted_eps": eps}


def _five_quarters():
    # oldest -> newest; revenue & net income grow, net margin improves
    return [
        _q("2024-12-31", 100.0, 40.0, 20.0, 10.0, 0.10),
        _q("2025-03-31", 110.0, 45.0, 23.0, 12.0, 0.12),
        _q("2025-06-30", 120.0, 50.0, 26.0, 14.0, 0.14),
        _q("2025-09-30", 130.0, 56.0, 30.0, 17.0, 0.17),
        _q("2025-12-31", 150.0, 66.0, 36.0, 22.0, 0.22),
    ]


def test_margins_computed_per_quarter():
    out = summarize_fundamentals(_five_quarters())
    last = out["quarters"][-1]
    assert last["gross_margin"] == round(66.0 / 150.0, 4)
    assert last["net_margin"] == round(22.0 / 150.0, 4)


def test_yoy_and_qoq_growth():
    out = summarize_fundamentals(_five_quarters())
    assert out["revenue_yoy"] == round(150.0 / 100.0 - 1, 4)        # newest vs 4 quarters ago
    assert out["net_income_yoy"] == round(22.0 / 10.0 - 1, 4)
    assert out["revenue_qoq"] == round(150.0 / 130.0 - 1, 4)


def test_net_margin_trend_improving():
    assert summarize_fundamentals(_five_quarters())["net_margin_trend"] == "improving"


def test_snapshot_and_next_earnings_passed_through():
    snap = {"trailing_pe": 30.0, "sector": "Technology"}
    out = summarize_fundamentals(_five_quarters(), snap, next_earnings="2026-07-30")
    assert out["snapshot"]["sector"] == "Technology" and out["next_earnings"] == "2026-07-30"


def test_handles_missing_fields_gracefully():
    # only revenue present -> margins None, growth still works where data exists
    qs = [{"period": "2025-09-30", "revenue": 100.0}, {"period": "2025-12-31", "revenue": 120.0}]
    out = summarize_fundamentals(qs)
    assert out["quarters"][-1].get("net_margin") is None
    assert abs(out["revenue_qoq"] - 0.2) < 1e-9
    assert out["revenue_yoy"] is None      # not enough quarters for YoY
