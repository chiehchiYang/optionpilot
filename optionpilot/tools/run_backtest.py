"""Tool: run_backtest — run the BacktestEngine and log the run to the ExperimentTracker.

Supports the ablation directly: call once with use_nudge=True and once False, then compare.

TODO: wire BacktestEngine + ExperimentTracker once predictions are available.
"""

from __future__ import annotations

from optionpilot.config import Config
from optionpilot.tools.base import ToolSpec

PARAMETERS = {
    "type": "object",
    "properties": {
        "symbol": {"type": "string"},
        "start": {"type": "string"},
        "end": {"type": "string"},
        "use_nudge": {"type": "boolean", "default": True},
        "threshold": {"type": "number", "default": 0.5},
    },
    "required": ["symbol", "start", "end"],
}


def build(config: Config) -> ToolSpec:
    def handler(symbol, start, end, use_nudge=True, threshold=0.5):
        raise NotImplementedError("run_backtest handler")

    return ToolSpec(
        name="run_backtest",
        description="Backtest the buy-point strategy over a date range and return metrics "
                    "(Sharpe, max drawdown, win rate, turnover). Logs the run for ablation.",
        parameters=PARAMETERS,
        handler=handler,
        tags=["backtest"],
    )
