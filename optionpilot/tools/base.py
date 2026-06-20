"""ToolSpec: the contract every tool implements, plus JSON-schema export for LLM tool calling.

Borrowed from ml-intern's tool model: each tool declares a name, description, JSON-schema
parameters, and whether it needs approval before running (e.g. expensive data pulls).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema for the arguments object
    handler: Callable[..., Any]
    requires_approval: bool = False
    tags: list[str] = field(default_factory=list)

    def to_openai_schema(self) -> dict[str, Any]:
        """OpenAI/LiteLLM function-tool schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def __call__(self, **kwargs: Any) -> Any:
        return self.handler(**kwargs)
