"""Test the Gradio streaming helpers with a fake agent loop (no gradio/browser needed)."""

import queue

from optionpilot.ui.app import stream_run


class FakeLoop:
    def __init__(self, events):
        self.events = events

    def run(self, message):
        self.events.put(("tool", "measure_vrp(ZETA)"))
        self.events.put(("tool", "run_backtest(ZETA)"))
        return "VERDICT: not enough edge."


def test_stream_run_streams_tools_then_verdict():
    events = queue.Queue()
    outs = list(stream_run(FakeLoop(events), events, "research ZETA"))
    assert len(outs) >= 2          # tool steps stream, then final verdict
    final = outs[-1]
    assert "measure_vrp" in final and "run_backtest" in final
    assert "VERDICT: not enough edge." in final


def test_stream_run_reports_errors():
    events = queue.Queue()

    class Boom:
        def __init__(self, ev): self.events = ev
        def run(self, m): raise RuntimeError("kaboom")

    final = list(stream_run(Boom(events), events, "x"))[-1]
    assert "kaboom" in final


def test_gui_ask_user_never_blocks():
    # in the GUI (interactive=False) ask_user must return a use-defaults note, never input()
    from optionpilot.config import Config
    from optionpilot.tools.ask_user import build
    out = build(Config.load(dotenv=False), interactive=False)(question="fixed or sweep?")
    assert "NO_INTERACTIVE_TERMINAL" in out
