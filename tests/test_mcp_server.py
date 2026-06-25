"""Tests for the MCP server's core session routing (no mcp package, no network)."""

from optionpilot.integrations.mcp_server import DeskSessions, research


class _FakeLoop:
    def __init__(self, desk):
        self.desk = desk
        self.calls = []

    def run(self, msg):
        self.calls.append(msg)
        return f"[{self.desk}] {msg}"


def _factory(_config, desk):
    return _FakeLoop(desk)


def test_session_reused_per_conversation_and_desk():
    s = DeskSessions(config=None, factory=_factory)
    a = s.loop_for("c1", "options")
    assert s.loop_for("c1", "options") is a          # same chat+desk -> same loop (memory)
    assert s.loop_for("c1", "crypto") is not a       # different desk -> separate loop
    assert s.loop_for("c2", "options") is not a      # different chat -> separate loop


def test_research_routes_to_desk_and_returns_text():
    s = DeskSessions(config=None, factory=_factory)
    assert research(s, "回測 ZETA", "c1", "options") == "[options] 回測 ZETA"
    assert research(s, "NOKUSDT", "c1", "crypto") == "[crypto] NOKUSDT"


def test_unknown_desk_falls_back_to_options():
    s = DeskSessions(config=None, factory=_factory)
    assert research(s, "hi", "c1", "nonsense").startswith("[options]")


def test_multi_turn_uses_same_loop():
    s = DeskSessions(config=None, factory=_factory)
    research(s, "first", "c1", "options")
    research(s, "second", "c1", "options")
    assert s.loop_for("c1", "options").calls == ["first", "second"]


def test_reset_clears_session():
    s = DeskSessions(config=None, factory=_factory)
    a = s.loop_for("c1", "options")
    assert s.reset("c1") == 1
    assert s.loop_for("c1", "options") is not a
