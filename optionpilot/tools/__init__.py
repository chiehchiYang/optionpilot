"""Tools layer: the core tools, plus a helper to register them on a ToolRouter."""

from __future__ import annotations

from optionpilot.config import Config
from optionpilot.tools import (
    ask_user,
    detect_unusual_activity,
    fetch_options_data,
    list_experiments,
    measure_vrp,
    run_backtest,
)
from optionpilot.tools.base import ToolSpec

_BUILDERS = [
    ask_user.build,
    fetch_options_data.build,
    run_backtest.build,
    detect_unusual_activity.build,
    measure_vrp.build,
    list_experiments.build,
]


def default_tools(config: Config, approve_spend=None) -> list[ToolSpec]:
    """Instantiate the core tools bound to the given config.

    approve_spend(message, usd) -> bool is consulted by data tools only when a paid download
    is about to happen (estimates and cache hits never prompt)."""
    return [build(config, approve_spend=approve_spend) for build in _BUILDERS]


def register_default_tools(router, config: Config, approve_spend=None) -> None:
    for spec in default_tools(config, approve_spend=approve_spend):
        router.register(spec)


__all__ = ["ToolSpec", "default_tools", "register_default_tools"]
