"""Tool: generate_report — assemble the strategy summary + ablation table + narrative.

Pulls runs from the ExperimentTracker, renders the nudge on/off comparison, and writes a
Markdown report under runs/. This is the agent's final deliverable.

TODO: implement Markdown rendering over ExperimentTracker.ablation_table().
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
        description="Generate a Markdown report: strategy summary, backtest metrics, and the "
                    "nudge ablation table with a narrative of what worked.",
        parameters=PARAMETERS,
        handler=handler,
        tags=["report"],
    )
