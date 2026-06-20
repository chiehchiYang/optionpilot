"""ToolRouter: registry + dispatch for tools, with approval gating.

Mirrors ml-intern's ToolRouter: the agent loop hands a tool name + args here; the router
validates the tool exists, runs approval gating if required, then executes and captures
the result (or a structured error string the LLM can read and recover from).
"""

from __future__ import annotations

import json
from typing import Any, Callable

from optionpilot.tools.base import ToolSpec


class ToolRouter:
    def __init__(self, approval_fn: Callable[[ToolSpec, dict[str, Any]], bool] | None = None):
        self._tools: dict[str, ToolSpec] = {}
        # approval_fn returns True to allow, False to deny. Default: allow all (headless).
        self._approval_fn = approval_fn or (lambda spec, args: True)

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"tool already registered: {spec.name}")
        self._tools[spec.name] = spec

    def specs(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def openai_schemas(self) -> list[dict[str, Any]]:
        return [s.to_openai_schema() for s in self._tools.values()]

    def dispatch(self, name: str, args: dict[str, Any]) -> str:
        """Execute a tool by name. Always returns a string for the LLM tool-result message."""
        spec = self._tools.get(name)
        if spec is None:
            return f"ERROR: unknown tool '{name}'. Available: {', '.join(self._tools)}"

        if spec.requires_approval and not self._approval_fn(spec, args):
            return f"DENIED: user declined to run '{name}' with args {json.dumps(args)}"

        try:
            result = spec(**args)
        except TypeError as e:
            return f"ERROR: bad arguments for '{name}': {e}"
        except Exception as e:  # noqa: BLE001 - surface to the LLM so it can recover
            return f"ERROR: '{name}' raised {type(e).__name__}: {e}"

        return result if isinstance(result, str) else json.dumps(result, default=str)
