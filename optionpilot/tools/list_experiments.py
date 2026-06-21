"""Tool: list_experiments — recall past backtest runs from the experiment DB for comparison."""

from __future__ import annotations

from optionpilot.config import Config
from optionpilot.tools.base import ToolSpec
from optionpilot.tracking import ExperimentTracker

PARAMETERS = {
    "type": "object",
    "properties": {
        "ticker": {"type": "string", "description": "Filter to one ticker (optional)."},
        "limit": {"type": "integer", "default": 20},
    },
}


def build(config: Config) -> ToolSpec:
    def handler(ticker=None, limit=20):
        db = config.runs_dir / "experiments.duckdb"
        if not db.exists():
            return {"runs": [], "note": "no experiments logged yet"}
        rows = ExperimentTracker(db).compare_runs(ticker=ticker, limit=limit)
        for r in rows:
            r["ts"] = str(r.get("ts"))
        return {"runs": rows, "count": len(rows)}

    return ToolSpec(
        name="list_experiments",
        description="List past backtest runs (ticker, params, key metrics) from the experiment "
                    "log so you can compare strategies/parameters you've already tested.",
        parameters=PARAMETERS,
        handler=handler,
        tags=["tracking"],
    )
