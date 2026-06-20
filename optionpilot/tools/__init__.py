"""Tools layer: the core tools, plus a helper to register them on a ToolRouter."""

from __future__ import annotations

from optionpilot.config import Config
from optionpilot.tools import (
    detect_unusual_activity,
    fetch_options_data,
    run_backtest,
)
from optionpilot.tools.base import ToolSpec

_BUILDERS = [
    fetch_options_data.build,
    run_backtest.build,
    detect_unusual_activity.build,
]


def default_tools(config: Config) -> list[ToolSpec]:
    """Instantiate the core tools bound to the given config."""
    return [build(config) for build in _BUILDERS]


def register_default_tools(router, config: Config) -> None:
    for spec in default_tools(config):
        router.register(spec)


__all__ = ["ToolSpec", "default_tools", "register_default_tools"]
