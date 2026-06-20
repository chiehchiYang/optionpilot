"""ExperimentTracker: persist each run's config + metrics so the planner can compare and the
report can build an ablation table.

Backed by DuckDB (one file under runs/). Each row = one backtest run: a config blob, the
metric summary, and whether nudge was enabled — exactly what the ablation needs.

TODO: implement log_run / query once the backtest produces metrics.
"""

from __future__ import annotations

from pathlib import Path


class ExperimentTracker:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    def log_run(self, config: dict, metrics: dict, nudge_enabled: bool) -> str:
        """Insert a run row; return its run id."""
        raise NotImplementedError("ExperimentTracker.log_run")

    def ablation_table(self) -> list[dict]:
        """Return rows for the nudge on/off comparison."""
        raise NotImplementedError("ExperimentTracker.ablation_table")
