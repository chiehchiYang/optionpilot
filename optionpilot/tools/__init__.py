"""Tools layer: the core tools, plus a helper to register them on a ToolRouter."""

from __future__ import annotations

from optionpilot.config import Config
from optionpilot.tools import (
    ask_user,
    detect_unusual_activity,
    fetch_options_data,
    list_experiments,
    measure_vrp,
    optimize_strategy,
    run_backtest,
)
from optionpilot.tools.base import ToolSpec

_BUILDERS = [
    ask_user.build,
    fetch_options_data.build,
    run_backtest.build,
    optimize_strategy.build,
    detect_unusual_activity.build,
    measure_vrp.build,
    list_experiments.build,
]


def default_tools(config: Config, approve_spend=None, interactive: bool = True) -> list[ToolSpec]:
    """Instantiate the core tools bound to the given config.

    approve_spend(message, usd) -> bool is consulted by data tools only when a paid download
    is about to happen. interactive=False (e.g. GUI) makes ask_user never block on terminal
    input — it returns a use-defaults note instead."""
    tools = []
    for build in _BUILDERS:
        if build is ask_user.build:
            tools.append(build(config, approve_spend=approve_spend, interactive=interactive))
        else:
            tools.append(build(config, approve_spend=approve_spend))
    return tools


def register_default_tools(router, config: Config, approve_spend=None, interactive: bool = True) -> None:
    for spec in default_tools(config, approve_spend=approve_spend, interactive=interactive):
        router.register(spec)


__all__ = ["ToolSpec", "default_tools", "register_default_tools"]
