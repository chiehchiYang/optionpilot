"""Research profiles — isolated agent personas backing the two GUI tabs / CLI modes.

Each profile bundles its own system prompt, playbook, and tool set, so the options desk and the
Binance perp desk never share context, instructions, or tools. build_loop() wires a profile into
a fresh ToolRouter + ExperimentLoop.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from optionpilot.agent.loop import (
    CRYPTO_SYSTEM_PROMPT,
    OPTIONS_SYSTEM_PROMPT,
    ExperimentLoop,
)
from optionpilot.agent.playbook import CRYPTO_PLAYBOOK, RESEARCH_PLAYBOOK
from optionpilot.agent.router import ToolRouter
from optionpilot.config import Config
from optionpilot.tools import CRYPTO_BUILDERS, OPTIONS_BUILDERS, register_tools


@dataclass(frozen=True)
class Profile:
    key: str               # stable id, e.g. "options" / "crypto"
    label: str             # display label (Traditional Chinese)
    blurb: str             # one-line GUI subtitle
    system_prompt: str
    playbook: str
    builders: tuple        # tool builder callables


OPTIONS_PROFILE = Profile(
    key="options",
    label="股票期權",
    blurb="美股期權策略研究:VRP 篩選、CSP/covered call/wheel 回測、walk-forward、圖表。",
    system_prompt=OPTIONS_SYSTEM_PROMPT,
    playbook=RESEARCH_PLAYBOOK,
    builders=tuple(OPTIONS_BUILDERS),
)

CRYPTO_PROFILE = Profile(
    key="crypto",
    label="幣安永續",
    blurb="Binance USDⓈ-M 永續合約(含美股永續)研究:資金費率 carry、網格回測。公開資料、不下單。",
    system_prompt=CRYPTO_SYSTEM_PROMPT,
    playbook=CRYPTO_PLAYBOOK,
    builders=tuple(CRYPTO_BUILDERS),
)

PROFILES: dict[str, Profile] = {p.key: p for p in (OPTIONS_PROFILE, CRYPTO_PROFILE)}


def build_loop(config: Config, profile: Profile, approve_spend=None, interactive: bool = True,
               on_event: Callable[[str, str], None] | None = None) -> ExperimentLoop:
    """Fresh router + loop for one profile — its own tools, prompt, and playbook."""
    router = ToolRouter()
    register_tools(router, config, list(profile.builders), approve_spend=approve_spend,
                   interactive=interactive)
    return ExperimentLoop(config, router, on_event=on_event,
                          system_prompt=profile.system_prompt, playbook=profile.playbook,
                          profile_key=profile.key)
