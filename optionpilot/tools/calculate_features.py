"""Tool: calculate_features — technical indicators + options-flow signals + greeks/IV.

Options-flow signals (put/call ratio, unusual-activity / volume spikes) are inspired by
retail options dashboards but here they are *features to be validated by backtest*, not
trusted blindly. Greeks/IV are computed locally (see data.greeks).

TODO: implement feature computation over a fetched DataFrame.
"""

from __future__ import annotations

from optionpilot.config import Config
from optionpilot.tools.base import ToolSpec

PARAMETERS = {
    "type": "object",
    "properties": {
        "symbol": {"type": "string"},
        "feature_sets": {
            "type": "array",
            "items": {"type": "string", "enum": ["technical", "options_flow", "greeks"]},
            "default": ["technical", "options_flow"],
        },
    },
    "required": ["symbol"],
}


def build(config: Config) -> ToolSpec:
    def handler(symbol, feature_sets=("technical", "options_flow")):
        raise NotImplementedError("calculate_features handler")

    return ToolSpec(
        name="calculate_features",
        description="Compute technical indicators, options-flow signals (put/call ratio, "
                    "unusual activity), and locally-computed greeks/IV for a symbol.",
        parameters=PARAMETERS,
        handler=handler,
        tags=["features"],
    )
