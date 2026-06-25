"""MCP server that exposes OptionPilot as a research specialist for a host agent (e.g. Hermes).

The host (Hermes) owns the conversation — messaging platforms, sessions, voice, white-listing —
and calls this server's `optionpilot_chat` tool to do the actual options/perp research. The full
OptionPilot discipline (playbook, tools, backtests, trajectory, cross-session memory) runs INSIDE
the tool, so we don't hand a pile of raw tools to the host LLM and lose the rigor.

Routing pattern (see docs/deploy_hermes.md): a Hermes `/op` skill flips the conversation into
"OptionPilot mode" and routes every message here until the user says 結束 / `/end`. State for that
mode lives host-side; the multi-turn RESEARCH session lives here (one loop per conversation+desk,
its ContextManager persisting across messages).

Safety: the MCP path runs FREE data sources only — paid Databento fetches are auto-denied — so a
message from the far end can never spend money. The core (DeskSessions / research) imports no mcp
package, so it's unit-testable without the optional dependency.
"""

from __future__ import annotations

from optionpilot.agent.profiles import PROFILES, build_loop
from optionpilot.config import Config


def _deny_paid(*_args, **_kwargs) -> bool:
    """approve_spend hook for the MCP path: never approve a paid (Databento) download."""
    return False


def _default_factory(config: Config, desk: str):
    profile = PROFILES.get(desk) or PROFILES["options"]
    return build_loop(config, profile, approve_spend=_deny_paid, interactive=False)


class DeskSessions:
    """Per-conversation OptionPilot loops, one per (conversation_id, desk), built lazily and kept
    so a conversation has continuity (each loop's ContextManager persists across messages)."""

    def __init__(self, config: Config | None, factory=_default_factory):
        self.config = config
        self.factory = factory
        self._loops: dict[tuple[str, str], object] = {}

    def loop_for(self, conversation_id: str, desk: str):
        key = (conversation_id, desk)
        if key not in self._loops:
            self._loops[key] = self.factory(self.config, desk)
        return self._loops[key]

    def reset(self, conversation_id: str, desk: str | None = None) -> int:
        gone = [k for k in self._loops
                if k[0] == conversation_id and (desk is None or k[1] == desk)]
        for k in gone:
            del self._loops[k]
        return len(gone)


def research(sessions: DeskSessions, message: str,
             conversation_id: str = "default", desk: str = "options") -> str:
    """Run one research turn on the right desk's persistent session and return the answer text."""
    desk = desk if desk in PROFILES else "options"
    return sessions.loop_for(conversation_id, desk).run(message)


_CHAT_DESC = (
    "Ask the OptionPilot research desk. Use this for ANY question about: stock OPTIONS strategies "
    "(cash-secured put, covered call, the wheel), implied vs realized vol / VRP, put-call ratio, "
    "support/resistance, BACKTESTING a strategy vs buy & hold; crypto/US-stock PERPETUALS (funding "
    "carry, grid bots, the composite/VIX regime); SCREENING stocks (hot/trending, multi-factor "
    "technical+fundamental+valuation), or a stock's recent FUNDAMENTALS/earnings. It runs a "
    "rigorous, backtest-validated research loop and returns the answer (a research desk, not a "
    "live trade signal; free data only). desk='options' (stocks) or 'crypto' (perps). Pass a "
    "stable conversation_id per chat so the session has memory across messages."
)


def build_mcp(config: Config | None = None):
    """Construct the FastMCP server. Imports mcp lazily so the core stays testable without it."""
    from mcp.server.fastmcp import FastMCP

    sessions = DeskSessions(config or Config.load())
    server = FastMCP("optionpilot")

    # Hermes registers MCP tools as mcp_<server>_<tool>, so these become mcp_optionpilot_chat /
    # mcp_optionpilot_reset.
    @server.tool(description=_CHAT_DESC)
    def chat(message: str, conversation_id: str = "default", desk: str = "options") -> str:
        return research(sessions, message, conversation_id, desk)

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
