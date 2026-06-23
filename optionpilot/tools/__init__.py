"""Tools layer: the core tools, grouped by research domain (options vs perp), plus helpers to
register a chosen tool set on a ToolRouter.

Two isolated tool sets back the two GUI tabs / agent profiles:
- OPTIONS_BUILDERS: stock-options research (VRP, CSP/CC/wheel backtests, charts, S/R…).
- CRYPTO_BUILDERS: Binance USDⓈ-M perpetuals (funding carry, grid backtest).
ask_user + list_experiments are shared by both.
"""

from __future__ import annotations

from optionpilot.config import Config
from optionpilot.tools import (
    ask_user,
    detect_unusual_activity,
    fetch_options_data,
    funding_analysis,
    grid_backtest,
    list_experiments,
    make_charts,
    market_sentiment,
    measure_vrp,
    optimize_strategy,
    regime_backtest,
    run_backtest,
    show_trajectory,
    support_resistance,
)
from optionpilot.tools.base import ToolSpec

# Options-desk tool set (the original default profile).
OPTIONS_BUILDERS = [
    ask_user.build,
    fetch_options_data.build,
    run_backtest.build,
    optimize_strategy.build,
    detect_unusual_activity.build,
    measure_vrp.build,
    make_charts.build,
    support_resistance.build,
    regime_backtest.build,
    market_sentiment.build,
    list_experiments.build,
    show_trajectory.build,
]

# Perp-desk tool set (isolated): Binance USDⓈ-M funding carry + grid backtest. Its perps are
# US-stock underlyings, so the equity fear gauge (VIX, via market_sentiment) is the right
# sentiment here — not crypto sentiment.
CRYPTO_BUILDERS = [
    ask_user.build,
    funding_analysis.build,
    grid_backtest.build,
    market_sentiment.build,
    list_experiments.build,
    show_trajectory.build,
]


def build_tools(config: Config, builders, approve_spend=None,
                interactive: bool = True) -> list[ToolSpec]:
    """Instantiate the given tool builders bound to config.

    approve_spend(message, usd) -> bool is consulted by data tools only when a paid download is
    about to happen. interactive=False (e.g. GUI) makes ask_user never block on terminal input."""
    tools = []
    for build in builders:
        if build is ask_user.build:
            tools.append(build(config, approve_spend=approve_spend, interactive=interactive))
        else:
            tools.append(build(config, approve_spend=approve_spend))
    return tools


def default_tools(config: Config, approve_spend=None, interactive: bool = True) -> list[ToolSpec]:
    """The options-desk tool set (the default profile)."""
    return build_tools(config, OPTIONS_BUILDERS, approve_spend=approve_spend,
                       interactive=interactive)


def register_tools(router, config: Config, builders, approve_spend=None,
                   interactive: bool = True) -> None:
    for spec in build_tools(config, builders, approve_spend=approve_spend, interactive=interactive):
        router.register(spec)


def register_default_tools(router, config: Config, approve_spend=None,
                           interactive: bool = True) -> None:
    register_tools(router, config, OPTIONS_BUILDERS, approve_spend=approve_spend,
                   interactive=interactive)


__all__ = ["ToolSpec", "OPTIONS_BUILDERS", "CRYPTO_BUILDERS", "build_tools", "default_tools",
           "register_tools", "register_default_tools"]
