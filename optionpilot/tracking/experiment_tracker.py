"""ExperimentTracker: persist each run's config + metrics so the planner can compare runs
and the report can build a comparison table.

Backed by DuckDB (one file under runs/). Each row = one backtest run: a config blob and the
metric summary, so different strategy variants can be compared head-to-head.

TODO: implement log_run / query once the backtest produces metrics.
"""

from __future__ import annotations

from pathlib import Path


class ExperimentTracker:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    def log_run(self, config: dict, metrics: dict) -> str:
        """Insert a run row; return its run id."""
        raise NotImplementedError("ExperimentTracker.log_run")

    def compare_runs(self) -> list[dict]:
        """Return run rows (config + metrics) for head-to-head comparison."""
        raise NotImplementedError("ExperimentTracker.compare_runs")
