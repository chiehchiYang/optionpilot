"""Tool: predict_buy_point — model signal for a symbol from its engineered features.

TODO: load a trained BaselineModel and run it over the feature rows.
"""

from __future__ import annotations

from optionpilot.config import Config
from optionpilot.tools.base import ToolSpec

PARAMETERS = {
    "type": "object",
    "properties": {
        "symbol": {"type": "string"},
    },
    "required": ["symbol"],
}


def build(config: Config) -> ToolSpec:
    def handler(symbol):
        raise NotImplementedError("predict_buy_point handler")

    return ToolSpec(
        name="predict_buy_point",
        description="Predict the trade signal for a symbol from its features.",
        parameters=PARAMETERS,
        handler=handler,
        tags=["model"],
    )
