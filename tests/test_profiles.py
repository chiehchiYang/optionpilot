"""The two research desks must stay ISOLATED: disjoint tools + their own prompt/playbook."""

from optionpilot.agent.profiles import CRYPTO_PROFILE, OPTIONS_PROFILE, PROFILES, build_loop
from optionpilot.config import Config
from optionpilot.tools import build_tools


def _names(profile):
    return {s.name for s in build_tools(Config.load(dotenv=False), list(profile.builders))}


def test_options_desk_has_options_tools_not_crypto():
    names = _names(OPTIONS_PROFILE)
    assert {"measure_vrp", "run_backtest", "make_charts"} <= names
    assert "funding_analysis" not in names and "grid_backtest" not in names


def test_crypto_desk_has_perp_tools_not_options():
    names = _names(CRYPTO_PROFILE)
    assert {"funding_analysis", "grid_backtest"} <= names
    assert "run_backtest" not in names and "measure_vrp" not in names
    # shared helpers are available on both desks
    assert {"ask_user", "list_experiments", "show_trajectory"} <= names


def test_profiles_have_distinct_prompts():
    assert OPTIONS_PROFILE.system_prompt != CRYPTO_PROFILE.system_prompt
    assert OPTIONS_PROFILE.playbook != CRYPTO_PROFILE.playbook
    assert set(PROFILES) == {"options", "crypto"}


def test_build_loop_uses_profile_prompt_and_tools():
    loop = build_loop(Config.load(dotenv=False), CRYPTO_PROFILE)
    sys_msg = loop.context.messages[0]["content"]
    assert "Perp Desk" in sys_msg                  # crypto system prompt injected
    assert "grid_backtest" in sys_msg              # crypto tools listed
    tool_names = {s.name for s in loop.router.specs()}
    assert "funding_analysis" in tool_names and "run_backtest" not in tool_names
