"""Approval gating for sensitive/expensive tool calls (e.g. paid Databento fetches).

Two built-in policies:
  - auto_approve: always allow (headless / --auto-approve).
  - interactive_approval: prompt on the terminal for tools marked requires_approval.

Phase 1 runs human-in-loop, so interactive_approval is the default in interactive mode.
"""

from __future__ import annotations

from typing import Any

from optionpilot.tools.base import ToolSpec


def auto_approve(spec: ToolSpec, args: dict[str, Any]) -> bool:
    return True


def interactive_approval(spec: ToolSpec, args: dict[str, Any]) -> bool:
    print(f"\n⚠  Tool '{spec.name}' requires approval.")
    print(f"   args: {args}")
    reply = input("   Allow? [y/N] ").strip().lower()
    return reply in ("y", "yes")
