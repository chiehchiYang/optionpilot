"""Tests for the MCP server's core session routing + GUI-style reply (no mcp package, no network)."""

from optionpilot.integrations.mcp_server import DeskSessions, research


class _FakeLoop:
    def __init__(self, desk, emit):
        self.desk = desk
        self.emit = emit
        self.calls = []

    def run(self, msg):
        self.calls.append(msg)
        self.emit(("tool", f"measure_vrp({msg})"))   # mimic on_event tool activity
        self.emit(("tool", "run_backtest(...)"))
        return f"[{self.desk}] verdict for {msg}"


def _factory(_config, desk, emit):
    return _FakeLoop(desk, emit)


def _sessions():
    return DeskSessions(config=None, factory=_factory)


def test_session_reused_per_conversation_and_desk():
    s = _sessions()
    a = s.loop_for("c1", "options")
    assert s.loop_for("c1", "options") is a          # same chat+desk -> same loop (memory)
    assert s.loop_for("c1", "crypto") is not a       # different desk -> separate loop
    assert s.loop_for("c2", "options") is not a      # different chat -> separate loop


def test_research_returns_text_and_charts_tuple():
    text, charts = research(_sessions(), "回測 ZETA", "c1", "options")
    assert text.strip().endswith("[options] verdict for 回測 ZETA")
    assert charts == []                              # config=None -> no chart dir


def test_reply_includes_tool_trace_like_the_gui():
    text, _ = research(_sessions(), "ZETA", "c1", "options", show_steps=True)
    assert "🔧 `tool` · measure_vrp(ZETA)" in text    # GUI-style step trace
    assert "run_backtest(...)" in text
    assert "---" in text                             # rule between trace and verdict


def test_show_steps_false_is_verdict_only():
    text, _ = research(_sessions(), "ZETA", "c1", "options", show_steps=False)
    assert text == "[options] verdict for ZETA"


def test_events_cleared_between_turns():
    s = _sessions()
    research(s, "AAA", "c1", "options")
    text, _ = research(s, "BBB", "c1", "options")     # only this turn's trace should show
    assert "AAA" not in text and "measure_vrp(BBB)" in text


def test_unknown_desk_falls_back_to_options():
    text, _ = research(_sessions(), "hi", "c1", "nonsense")
    assert "[options]" in text


def test_multi_turn_uses_same_loop():
    s = _sessions()
    research(s, "first", "c1", "options")
    research(s, "second", "c1", "options")
    assert s.loop_for("c1", "options").calls == ["first", "second"]


def test_reset_clears_session_and_events():
    s = _sessions()
    a = s.loop_for("c1", "options")
    assert s.reset("c1") == 1
    assert s.loop_for("c1", "options") is not a