"""Tests for ExperimentTracker (DuckDB) and the Markdown report writer."""

from optionpilot.tracking import ExperimentTracker
from optionpilot.tracking.report import write_backtest_report

METRICS = {
    "n_trades": 19, "win_rate": 0.84, "assigned_rate": 0.21, "total_return": 0.2298,
    "benchmark_buy_hold": 1.0078, "excess_vs_buy_hold": -0.778, "sharpe_annualized": 0.6456,
    "max_drawdown": -0.2289, "worst_trade": -0.2289,
}
PARAMS = {"target_moneyness": 0.95, "dte_min": 25, "dte_max": 45}


def test_tracker_log_and_compare(tmp_path):
    t = ExperimentTracker(tmp_path / "exp.duckdb")
    rid1 = t.log_run("ZETA", "cash_secured_put", PARAMS, METRICS)
    rid2 = t.log_run("AAPL", "cash_secured_put", PARAMS, {**METRICS, "excess_vs_buy_hold": 0.05})
    assert rid1 != rid2

    allruns = t.compare_runs()
    assert len(allruns) == 2
    zeta = t.compare_runs(ticker="ZETA")
    assert len(zeta) == 1 and zeta[0]["ticker"] == "ZETA"
    assert zeta[0]["excess_vs_buy_hold"] == -0.778
    # persists across instances (same DB file)
    assert len(ExperimentTracker(tmp_path / "exp.duckdb").compare_runs()) == 2


def test_report_writer(tmp_path):
    trades = [{"entry": "2024-10-21", "expiry": "2024-11-15", "strike": 25.0,
               "underlying_at_expiry": 17.58, "assigned": True, "return": -0.2289}]
    p = write_backtest_report(tmp_path, "ZETA", "cash_secured_put", PARAMS, METRICS,
                              trades, "abc123", "2023-01-01", "2025-01-01")
    assert p.exists()
    text = p.read_text()
    assert "UNDERPERFORMS buy & hold" in text
    assert "abc123" in text and "ZETA" in text
