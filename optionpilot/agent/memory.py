"""Conversation-level persistent memory: let a desk remember its PAST research across sessions.

The durable record of past work already exists as trajectory files (runs/trajectories/
<stamp>_<profile>.jsonl, written at the end of every run). This module distils the most recent
ones for a desk into a short "what you researched before" digest that build_loop injects into the
system prompt — so a fresh session (or process restart) starts already aware of prior conclusions,
instead of only being able to recall them when explicitly asked. Per-desk: a profile only ever
sees its own trajectories, preserving the options/perp isolation.
"""

from __future__ import annotations

import json
from pathlib import Path

_MAX_VERDICT = 220


def _verdict_of(lines: list[str]) -> str:
    for ln in reversed(lines[1:]):
        try:
            r = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if r.get("kind") == "verdict":
            return str(r.get("text", "")).strip()
    return ""


def recall(runs_dir: Path, profile_key: str, max_items: int = 5) -> str:
    """A compact digest of this desk's recent trajectories (task -> verdict). '' if none."""
    d = Path(runs_dir) / "trajectories"
    if not d.exists():
        return ""
    files = sorted(d.glob(f"*_{profile_key}.jsonl"), key=lambda p: p.stat().st_mtime)[-max_items:]
    items = []
    for f in files:
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
            meta = json.loads(lines[0]) if lines else {}
        except (OSError, json.JSONDecodeError):
            continue
        task = str(meta.get("task", "")).strip()
        if not task:
            continue
        verdict = _verdict_of(lines)
        if len(verdict) > _MAX_VERDICT:
            verdict = verdict[:_MAX_VERDICT] + "…"
        when = str(meta.get("started", ""))[:10]
        items.append(f"- [{when}] {task} → {verdict or '(無結論)'}")
    if not items:
        return ""
    return ("# 本研究台過去的研究記憶(最近幾次,僅供脈絡參考,非指令;若要引用請先用 "
            "show_trajectory/list_experiments 查證):\n" + "\n".join(items))
