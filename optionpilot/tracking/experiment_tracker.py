"""ExperimentTracker: persist each backtest run (config + metrics) to DuckDB so runs can be
compared head-to-head later.

One row per run. Key metrics are stored as columns for easy comparison; the full params/metrics
blobs are kept as JSON for completeness.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path


class ExperimentTracker:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self):
        import duckdb

        return duckdb.connect(str(self.db_path))

    def _init(self) -> None:
        con = self._connect()
        try:
            con.execute(
                """CREATE TABLE IF NOT EXISTS runs (
                    run_id VARCHAR, ts TIMESTAMP, ticker VARCHAR, strategy VARCHAR,
                    params JSON, metrics JSON,
                    n_trades INTEGER, total_return DOUBLE, benchmark_buy_hold DOUBLE,
                    excess_vs_buy_hold DOUBLE, sharpe DOUBLE, max_drawdown DOUBLE
                )"""
            )
        finally:
            con.close()

    def log_run(self, ticker: str, strategy: str, params: dict, metrics: dict) -> str:
        run_id = uuid.uuid4().hex[:12]
        con = self._connect()
        try:
            con.execute(
                "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                [run_id, datetime.now(), ticker.upper(), strategy,
                 json.dumps(params), json.dumps(metrics),
                 metrics.get("n_trades"), metrics.get("total_return"),
                 metrics.get("benchmark_buy_hold"), metrics.get("excess_vs_buy_hold"),
                 metrics.get("sharpe_annualized"), metrics.get("max_drawdown")],
            )
        finally:
            con.close()
        return run_id

    def compare_runs(self, ticker: str | None = None, limit: int = 20) -> list[dict]:
        con = self._connect()
        try:
            q = ("SELECT run_id, ts, ticker, strategy, n_trades, total_return, "
                 "benchmark_buy_hold, excess_vs_buy_hold, sharpe, max_drawdown FROM runs")
            params: list = []
            if ticker:
                q += " WHERE ticker = ?"
                params.append(ticker.upper())
            q += " ORDER BY ts DESC LIMIT ?"
            params.append(limit)
            cur = con.execute(q, params)
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
        finally:
            con.close()
        return [dict(zip(cols, r)) for r in rows]
