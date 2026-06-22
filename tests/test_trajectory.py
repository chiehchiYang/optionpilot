"""Tests for the research-path recorder (Trajectory): nodes, serialization, persistence."""

import json

from optionpilot.agent.trajectory import Trajectory


def _sample():
    t = Trajectory(task="研究 NOKUSDT 網格", profile="crypto", started="2026-06-22T00:00:00")
    t.add("task", "研究 NOKUSDT 網格")
    t.plan(hypothesis="高 funding 可被網格吃下", change="grid_backtest NOKUSDT 1h", rationale="先看震盪")
    t.decision("我要先回測網格")
    t.tool("grid_backtest", {"symbol": "NOKUSDT", "interval": "1h"}, {"total_return": -0.05})
    t.verdict("網格優於買進持有但仍虧損")
    return t


def test_trajectory_records_ordered_nodes():
    t = _sample()
    assert [s.kind for s in t.steps] == ["task", "plan", "decision", "tool", "verdict"]
    assert t.counts() == {"task": 1, "plan": 1, "decision": 1, "tool": 1, "verdict": 1}


def test_tool_result_is_truncated():
    t = Trajectory()
    t.tool("x", {"a": 1}, "y" * 5000, max_result=100)
    assert len(t.steps[-1].data["result"]) <= 101  # 100 + ellipsis


def test_jsonl_has_meta_header_then_rows():
    t = _sample()
    lines = t.to_jsonl().splitlines()
    meta = json.loads(lines[0])
    assert meta["kind"] == "_meta" and meta["profile"] == "crypto"
    assert meta["counts"]["plan"] == 1
    assert len(lines) == 1 + len(t.steps)
    # plan row carries its structured fields
    plan_row = json.loads(lines[2])
    assert plan_row["kind"] == "plan" and plan_row["change"] == "grid_backtest NOKUSDT 1h"


def test_markdown_renders_path():
    md = _sample().to_markdown()
    assert "# 研究路徑" in md and "🧭 規劃" in md and "🔧 工具" in md and "✅ 結論" in md
    assert "grid_backtest" in md


def test_save_writes_jsonl_and_markdown(tmp_path):
    paths = _sample().save(tmp_path, stamp="20260622_000000")
    assert paths["jsonl"].exists() and paths["md"].exists()
    assert paths["md"].name == "20260622_000000_crypto.md"
    assert "研究路徑" in paths["md"].read_text(encoding="utf-8")
