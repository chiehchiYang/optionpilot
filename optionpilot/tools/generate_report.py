"""Tool: generate_report — assemble the strategy summary + run comparison + narrative.

Pulls runs from the ExperimentTracker, renders a comparison of their metrics, and writes a
Markdown report under runs/. This is the agent's final deliverable.

TODO: implement Markdown rendering over ExperimentTracker run history.
"""

from __future__ import annotations

from optionpilot.config import Config
from optionpilot.tools.base import ToolSpec

PARAMETERS = {
    "type": "object",
    "properties": {
        "symbol": {"type": "string"},
        "title": {"type": "string", "default": "OptionPilot strategy report"},
    },
    "required": ["symbol"],
}


def build(config: Config) -> ToolSpec:
    def handler(symbol, title="OptionPilot strategy report"):
        raise NotImplementedError("generate_report handler")

    return ToolSpec(
        name="generate_report",
        description="Generate a Markdown report: strategy summary, backtest metrics, and a "
                    "comparison across runs with a narrative of what worked.",
        parameters=PARAMETERS,
        handler=handler,
        tags=["report"],
    )
