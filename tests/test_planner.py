"""Tests for the Planner (next-experiment proposer) with a fake LLM."""

from types import SimpleNamespace

from optionpilot.agent.planner import Planner


class FakeLLM:
    def __init__(self, content):
        self.content = content

    def complete(self, messages, **kw):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))])


def test_planner_parses_proposal():
    llm = FakeLLM('{"done": false, "hypothesis": "wider DTE helps", '
                  '"change": "dte 7-21", "rationale": "more samples"}')
    p = Planner(llm).propose_next("research ZETA CSP", [{"params": {}, "metrics": {}}])
    assert p.done is False and "dte" in p.change.lower()


def test_planner_handles_code_fence_and_done():
    llm = FakeLLM('```json\n{"done": true, "hypothesis": "", "change": "", '
                  '"rationale": "enough evidence"}\n```')
    p = Planner(llm).propose_next("q", [])
    assert p.done is True and "enough" in p.rationale


def test_planner_unparseable_output_is_not_done():
    llm = FakeLLM("I think you should try a wider DTE window.")
    p = Planner(llm).propose_next("q", [])
    assert p.done is False
