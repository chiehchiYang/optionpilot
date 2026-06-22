"""Trajectory: record one agent run's research PATH as inspectable, persisted nodes.

A run's path is an ordered sequence of typed steps — the task, each planning decision
(hypothesis/change/rationale), each tool call with its args + result summary, and the final
verdict. It is persisted under runs/trajectories/ as JSONL (machine-readable) + Markdown
(human-readable) so you can review HOW the intern reached its conclusion, not just the answer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# step kind -> Markdown heading glyph + label
_GLYPH = {
    "task": ("🎯", "任務"),
    "plan": ("🧭", "規劃"),
    "decision": ("🤔", "決策"),
    "tool": ("🔧", "工具"),
    "verdict": ("✅", "結論"),
    "note": ("📝", "註記"),
}


@dataclass
class Step:
    kind: str
    text: str = ""
    data: dict[str, Any] = field(default_factory=dict)


class Trajectory:
    def __init__(self, task: str = "", profile: str = "", started: str = ""):
        self.task = task
        self.profile = profile
        self.started = started or datetime.now().isoformat(timespec="seconds")
        self.steps: list[Step] = []

    # --- recording ---
    def add(self, kind: str, text: str = "", **data: Any) -> Step:
        self.steps.append(Step(kind=kind, text=text, data=data))
        return self.steps[-1]

    def plan(self, hypothesis: str, change: str, rationale: str, done: bool = False) -> Step:
        return self.add("plan", hypothesis, change=change, rationale=rationale, done=done)

    def decision(self, text: str) -> Step:
        return self.add("decision", text)

    def tool(self, name: str, args: Any, result: Any, max_result: int = 600) -> Step:
        r = str(result)
        if len(r) > max_result:
            r = r[:max_result] + "…"
        return self.add("tool", name, args=args, result=r)

    def verdict(self, text: str) -> Step:
        return self.add("verdict", text)

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for s in self.steps:
            out[s.kind] = out.get(s.kind, 0) + 1
        return out

    # --- serialization ---
    def to_dicts(self) -> list[dict]:
        return [{"kind": s.kind, "text": s.text, **s.data} for s in self.steps]

    def to_jsonl(self) -> str:
        meta = {"kind": "_meta", "task": self.task, "profile": self.profile,
                "started": self.started, "counts": self.counts()}
        rows = [meta, *self.to_dicts()]
        return "\n".join(json.dumps(r, ensure_ascii=False, default=str) for r in rows)

    def to_markdown(self) -> str:
        lines = [f"# 研究路徑 · {self.task or '(未命名任務)'}", ""]
        c = self.counts()
        summary = "、".join(f"{_GLYPH.get(k, ('•', k))[1]}×{v}" for k, v in c.items())
        lines += [f"- 研究台:`{self.profile or 'run'}`  ·  開始:{self.started}",
                  f"- 步數:{len(self.steps)}（{summary}）", ""]
        for i, s in enumerate(self.steps, 1):
            glyph, label = _GLYPH.get(s.kind, ("•", s.kind))
            if s.kind == "plan":
                done = "（判定:已足夠，收尾）" if s.data.get("done") else ""
                lines.append(f"### {i}. {glyph} {label} {done}")
                if s.text:
                    lines.append(f"- 假設:{s.text}")
                if s.data.get("change"):
                    lines.append(f"- 下一步:{s.data['change']}")
                if s.data.get("rationale"):
                    lines.append(f"- 理由:{s.data['rationale']}")
            elif s.kind == "tool":
                args = json.dumps(s.data.get("args", {}), ensure_ascii=False, default=str)
                lines.append(f"### {i}. {glyph} {label} · `{s.text}`")
                lines.append(f"- 參數:`{args}`")
                lines.append(f"- 結果:{s.data.get('result', '')}")
            else:
                lines.append(f"### {i}. {glyph} {label}")
                if s.text:
                    lines.append(s.text)
            lines.append("")
        return "\n".join(lines)

    def save(self, out_dir: Path, stamp: str | None = None) -> dict[str, Path]:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = stamp or datetime.now().strftime("%Y%m%d_%H%M%S")
        base = f"{stamp}_{self.profile or 'run'}"
        jp, mp = out_dir / f"{base}.jsonl", out_dir / f"{base}.md"
        jp.write_text(self.to_jsonl(), encoding="utf-8")
        mp.write_text(self.to_markdown(), encoding="utf-8")
        return {"jsonl": jp, "md": mp}
