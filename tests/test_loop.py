"""ExperimentLoop tests with a scripted fake LLM (no network).

The fake mimics the LiteLLM response shape (resp.choices[0].message with .content and
.tool_calls[*].function.{name,arguments}) so we exercise the real loop control flow.
"""

from types import SimpleNamespace

import pytest

from optionpilot.agent.loop import ExperimentLoop
from optionpilot.agent.router import ToolRouter
from optionpilot.config import Config
from optionpilot.tools.base import ToolSpec


def _msg(content=None, tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls)


def _resp(msg):
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def _toolcall(call_id, name, arguments):
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=arguments))


class FakeLLM:
    def __init__(self, scripted):
        self.scripted = list(scripted)
        self.calls = 0

    def complete(self, messages, tools=None, **kw):
        self.calls += 1
        return self.scripted.pop(0)


def _echo_router():
    seen = []

    def handler(**kwargs):
        seen.append(kwargs)
        return {"ok": True, **kwargs}

    router = ToolRouter()
    router.register(ToolSpec(
        name="echo_tool", description="echo", handler=handler,
        parameters={"type": "object", "properties": {"x": {"type": "integer"}}},
    ))
    return router, seen


def _loop(router, scripted):
    cfg = Config.load(dotenv=False)
    return ExperimentLoop(cfg, router, llm=FakeLLM(scripted), on_event=lambda k, t: None,
                          persist_trajectory=False)


def test_runs_tool_then_returns_final_answer():
    router, seen = _echo_router()
    scripted = [
        _resp(_msg(content="", tool_calls=[_toolcall("c1", "echo_tool", '{"x": 7}')])),
        _resp(_msg(content="done: 7")),
    ]
    loop = _loop(router, scripted)
    out = loop.run("do the thing")
    assert out == "done: 7"
    assert seen == [{"x": 7}]  # tool actually dispatched with parsed args
    # transcript has a tool-result message tied to the call id
    assert any(m.get("role") == "tool" and m.get("tool_call_id") == "c1"
               for m in loop.context.messages)


def test_bad_json_args_recovers():
    router, seen = _echo_router()
    scripted = [
        _resp(_msg(content="", tool_calls=[_toolcall("c1", "echo_tool", "not json")])),
        _resp(_msg(content="recovered")),
    ]
    loop = _loop(router, scripted)
    out = loop.run("oops")
    assert out == "recovered"
    assert seen == []  # tool never ran on bad args
    assert any("not valid JSON" in str(m.get("content")) for m in loop.context.messages)


def test_doom_loop_blocks_repeated_identical_call():
    router, seen = _echo_router()
    same = lambda: _toolcall("c", "echo_tool", '{"x": 1}')
    scripted = [
        _resp(_msg(content="", tool_calls=[same()])),  # 1: runs
        _resp(_msg(content="", tool_calls=[same()])),  # 2: runs
        _resp(_msg(content="", tool_calls=[same()])),  # 3: blocked by doom-loop
        _resp(_msg(content="stopping")),
    ]
    loop = _loop(router, scripted)
    out = loop.run("loop please")
    assert out == "stopping"
    assert len(seen) == 2  # third identical call was blocked, not dispatched
    assert any("loop detected" in str(m.get("content")) for m in loop.context.messages)


def test_run_records_trajectory():
    router, _ = _echo_router()
    scripted = [
        _resp(_msg(content="I will echo 7", tool_calls=[_toolcall("c1", "echo_tool", '{"x": 7}')])),
        _resp(_msg(content="done: 7")),
    ]
    loop = _loop(router, scripted)
    loop.run("do the thing")
    kinds = [s.kind for s in loop.trajectory.steps]
    assert kinds == ["task", "decision", "tool", "verdict"]
    tool_step = loop.trajectory.steps[2]
    assert tool_step.text == "echo_tool" and tool_step.data["args"] == {"x": 7}
    assert loop.trajectory.steps[-1].text == "done: 7"


def test_run_planned_records_plan_nodes():
    router, _ = _echo_router()
    # planner round 1 -> propose; react -> answer; planner round 2 -> done; final synth -> verdict
    scripted = [
        _resp(_msg(content='{"done": false, "hypothesis": "h1", "change": "echo 7", '
                           '"rationale": "r1"}')),                       # planner round 1
        _resp(_msg(content="", tool_calls=[_toolcall("c1", "echo_tool", '{"x": 7}')])),  # react
        _resp(_msg(content="round1 result")),                            # react answer
        _resp(_msg(content='{"done": true, "hypothesis": "", "change": "", "rationale": "enough"}')),
        _resp(_msg(content="final honest verdict")),                     # synthesis react
    ]
    loop = _loop(router, scripted)
    out = loop.run_planned("research it", max_rounds=3)
    assert out == "final honest verdict"
    plans = [s for s in loop.trajectory.steps if s.kind == "plan"]
    assert len(plans) == 2                       # one proposal + one done
    assert plans[0].text == "h1" and plans[0].data["change"] == "echo 7"
    assert plans[1].data["done"] is True
    assert loop.trajectory.steps[-1].kind == "verdict"
