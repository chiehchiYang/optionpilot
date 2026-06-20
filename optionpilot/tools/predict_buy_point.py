"""Tool: predict_buy_point — baseline model probability passed through the NudgeLayer.

Returns both raw and nudged probabilities so the ablation is visible at the call site.

TODO: load a trained BaselineModel + configured NudgeLayer and run them over features.
"""

from __future__ import annotations

from optionpilot.config import Config
from optionpilot.tools.base import ToolSpec

PARAMETERS = {
    "type": "object",
    "properties": {
        "symbol": {"type": "string"},
        "use_nudge": {"type": "boolean", "default": True,
                      "description": "Apply the NudgeLayer; set False for the ablation baseline."},
    },
    "required": ["symbol"],
}


def build(config: Config) -> ToolSpec:
    def handler(symbol, use_nudge=True):
        raise NotImplementedError("predict_buy_point handler")

    return ToolSpec(
        name="predict_buy_point",
        description="Predict buy-point probability for a symbol; optionally apply the Nudge "
                    "post-processing layer. Returns raw and nudged probabilities.",
        parameters=PARAMETERS,
        handler=handler,
        tags=["model"],
    )
