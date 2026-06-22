"""Tool: show_trajectory — recall a past run's research PATH (the recorded trajectory).

Each run saves its path to runs/trajectories/<stamp>_<profile>.md (+ .jsonl). This tool lets
the agent surface "how did I get here" on request: the latest path, a named one, or a list.
"""

from __future__ import annotations

from optionpilot.config import Config
from optionpilot.tools.base import ToolSpec

PARAMETERS = {
    "type": "object",
    "properties": {
        "which": {"type": "string", "enum": ["latest", "list"], "default": "latest",
                  "description": "'latest' returns the most recent research path; 'list' lists "
                                 "available ones."},
        "name": {"type": "string", "description": "A specific trajectory file stem to load "
                                                  "(overrides 'which')."},
    },
}


def build(config: Config, approve_spend=None) -> ToolSpec:
    def handler(which="latest", name=None):
        d = config.runs_dir / "trajectories"
        files = sorted(d.glob("*.md"), key=lambda p: p.stat().st_mtime) if d.exists() else []
        if not files:
            return {"trajectories": [], "note": "尚未有任何研究路徑記錄(跑一次研究後就會產生)"}
        if name:
            match = [p for p in files if p.stem == name or p.name == name]
            if not match:
                return {"note": f"找不到 '{name}'", "available": [p.stem for p in files]}
            target = match[-1]
        elif which == "list":
            return {"trajectories": [p.stem for p in reversed(files)], "count": len(files)}
        else:
            target = files[-1]
        return {"name": target.stem, "path": str(target),
                "markdown": target.read_text(encoding="utf-8")}

    return ToolSpec(
        name="show_trajectory",
        description="Show a past run's research PATH (the recorded trajectory: task → planning "
                    "→ tool calls → verdict). Use when the user asks how a conclusion was "
                    "reached, to see the research process, or 研究路徑/過程. 'which=list' lists "
                    "saved paths; 'name' loads a specific one.",
        parameters=PARAMETERS,
        handler=handler,
        tags=["tracking"],
    )
