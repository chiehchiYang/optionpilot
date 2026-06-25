"""MCP server that exposes OptionPilot as a research specialist for a host agent (e.g. Hermes).

The host (Hermes) owns the conversation — messaging platforms, sessions, voice, white-listing —
and calls this server's `chat` tool to do the actual options/perp research. The full OptionPilot
discipline (playbook, tools, backtests, trajectory, cross-session memory) runs INSIDE the tool, so
we don't hand a pile of raw tools to the host LLM and lose the rigor.

Reply mode mirrors the Gradio GUI: the tool-activity trace (🔧 …) + the final verdict + any charts
the run produced (as image content). The ONE difference from the GUI is liveness — a single MCP
call returns once, so the trace arrives WITH the verdict, not streamed step-by-step. Tune with
OPTIONPILOT_MCP_SHOW_STEPS / OPTIONPILOT_MCP_RETURN_IMAGES (default both on). One difference we keep
ON PURPOSE: FREE data only — paid Databento fetches are auto-denied (the GUI auto-approves), so a
far-end message can never spend money.

The core (DeskSessions / research) imports no mcp package, so it's unit-testable without the dep.
"""

from __future__ import annotations

import os

from optionpilot.agent.profiles import PROFILES, build_loop
from optionpilot.config import Config


def _deny_paid(*_args, **_kwargs) -> bool:
    """approve_spend hook for the MCP path: never approve a paid (Databento) download."""
    return False


def _default_factory(config: Config, desk: str, emit):
    """Build a loop for `desk` whose tool activity is pushed to `emit((kind, text))`."""
    profile = PROFILES.get(desk) or PROFILES["options"]
    return build_loop(config, profile, approve_spend=_deny_paid, interactive=False,
                      on_event=lambda kind, text: emit((kind, text)))


def _chart_paths(config: Config | None) -> set:
    if config is None:
        return set()
    d = config.runs_dir / "charts"
    return set(d.glob("*.png")) if d.exists() else set()


def _compose(events: list, verdict: str, show_steps: bool) -> str:
    """Same shape as the GUI's final bubble: tool trace, a rule, then the verdict."""
    if show_steps and events:
        steps = "\n\n".join(f"🔧 `{kind}` · {text}" for kind, text in events)
        return f"{steps}\n\n---\n\n{verdict}".strip()
    return verdict


class DeskSessions:
    """Per-conversation OptionPilot loops, one per (conversation_id, desk), built lazily and kept
    so a conversation has continuity (each loop's ContextManager persists across messages). Each
    loop has its own event sink, cleared before every turn so we capture just that turn's trace."""

    def __init__(self, config: Config | None, factory=_default_factory):
        self.config = config
        self.factory = factory
        self._loops: dict[tuple[str, str], object] = {}
        self._events: dict[tuple[str, str], list] = {}

    def loop_for(self, conversation_id: str, desk: str):
        key = (conversation_id, desk)
        if key not in self._loops:
            events: list = []
            self._loops[key] = self.factory(self.config, desk, events.append)
            self._events[key] = events
        return self._loops[key]

    def events_for(self, conversation_id: str, desk: str) -> list:
        return self._events[(conversation_id, desk)]

    def reset(self, conversation_id: str, desk: str | None = None) -> int:
        gone = [k for k in self._loops
                if k[0] == conversation_id and (desk is None or k[1] == desk)]
        for k in gone:
            del self._loops[k]
            self._events.pop(k, None)
        return len(gone)


def research(sessions: DeskSessions, message: str, conversation_id: str = "default",
             desk: str = "options", show_steps: bool = True) -> tuple[str, list[str]]:
    """Run one research turn and return (reply_text, chart_png_paths). reply_text mirrors the GUI:
    the turn's tool trace + the verdict; chart paths are whatever the run newly created."""
    desk = desk if desk in PROFILES else "options"
    loop = sessions.loop_for(conversation_id, desk)
    events = sessions.events_for(conversation_id, desk)
    events.clear()
    before = _chart_paths(sessions.config)
    try:
        verdict = loop.run(message)
    except Exception as e:  # noqa: BLE001 - surface errors as text, like the GUI does
        verdict = f"⚠️ error: {e}"
    new_charts = sorted(_chart_paths(sessions.config) - before, key=lambda p: p.stat().st_mtime)
    return _compose(list(events), verdict, show_steps), [str(p) for p in new_charts]


_CHAT_DESC = (
    "Ask the OptionPilot research desk. Use this for ANY question about: stock OPTIONS strategies "
    "(cash-secured put, covered call, the wheel), implied vs realized vol / VRP, put-call ratio, "
    "support/resistance, BACKTESTING a strategy vs buy & hold; crypto/US-stock PERPETUALS (funding "
    "carry, grid bots, the composite/VIX regime); SCREENING stocks (hot/trending, multi-factor "
    "technical+fundamental+valuation), or a stock's recent FUNDAMENTALS/earnings. It runs a "
    "rigorous, backtest-validated research loop and returns its working trace, the answer, and any "
    "charts (a research desk, not a live trade signal; free data only). desk='options' (stocks) or "
    "'crypto' (perps). Pass a stable conversation_id per chat so the session has memory."
)


def build_mcp(config: Config | None = None):
    """Construct the FastMCP server. Imports mcp lazily so the core stays testable without it."""
    from mcp.server.fastmcp import Image
    from mcp.server.fastmcp import FastMCP

    sessions = DeskSessions(config or Config.load())
    show_steps = os.getenv("OPTIONPILOT_MCP_SHOW_STEPS", "1") != "0"
    return_images = os.getenv("OPTIONPILOT_MCP_RETURN_IMAGES", "1") != "0"
    server = FastMCP("optionpilot")

    # Hermes registers MCP tools as mcp_<server>_<tool> -> mcp_optionpilot_chat / _reset.
    @server.tool(description=_CHAT_DESC)
    def chat(message: str, conversation_id: str = "default", desk: str = "options"):
        text, charts = research(sessions, message, conversation_id, desk, show_steps=show_steps)
        if return_images and charts:
            return [text, *[Image(path=p) for p in charts]]
        return text

    @server.tool(description="Clear the OptionPilot conversation session (start the research "
                             "context fresh for this chat).")
    def reset(conversation_id: str = "default") -> str:
        n = sessions.reset(conversation_id)
        return f"已清除 {n} 個 OptionPilot session。"

    return server


def main():
    build_mcp().run()


if __name__ == "__main__":
    main()
