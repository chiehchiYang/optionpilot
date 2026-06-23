"""Tests for conversation-level persistent memory (per-desk recall from trajectories)."""

from optionpilot.agent.memory import recall
from optionpilot.agent.profiles import OPTIONS_PROFILE, build_loop
from optionpilot.agent.trajectory import Trajectory
from optionpilot.config import Config


def _save(runs_dir, profile, task, verdict, stamp):
    t = Trajectory(task=task, profile=profile)
    t.add("task", task)
    t.verdict(verdict)
    t.save(runs_dir / "trajectories", stamp=stamp)


def test_recall_empty_when_no_history(tmp_path):
    assert recall(tmp_path, "options") == ""


def test_recall_digest_has_task_and_verdict(tmp_path):
    _save(tmp_path, "options", "研究 ZETA wheel", "+12% 但樣本外過擬合", "20260101_000000")
    dig = recall(tmp_path, "options")
    assert "ZETA wheel" in dig and "過擬合" in dig and "研究記憶" in dig


def test_recall_is_per_desk(tmp_path):
    _save(tmp_path, "options", "ZETA put 研究", "options 結論", "20260101_000000")
    _save(tmp_path, "crypto", "NOKUSDT 網格", "crypto 結論", "20260101_000001")
    opt, cry = recall(tmp_path, "options"), recall(tmp_path, "crypto")
    assert "ZETA put 研究" in opt and "NOKUSDT 網格" not in opt
    assert "NOKUSDT 網格" in cry and "ZETA put 研究" not in cry


def test_recall_respects_max_items(tmp_path):
    for i in range(7):
        _save(tmp_path, "options", f"task{i}", f"v{i}", f"2026010{i}_000000")
    dig = recall(tmp_path, "options", max_items=3)
    assert dig.count("- [") == 3   # only the cap is kept, regardless of which


def test_build_loop_injects_memory_into_system_prompt(tmp_path):
    _save(tmp_path, "options", "ZETA wheel 研究", "結論:過擬合", "20260101_000000")
    cfg = Config(**{**Config.load(dotenv=False).__dict__, "runs_dir": tmp_path})
    loop = build_loop(cfg, OPTIONS_PROFILE)
    sys_msg = loop.context.messages[0]["content"]
    assert "ZETA wheel 研究" in sys_msg and "研究記憶" in sys_msg
