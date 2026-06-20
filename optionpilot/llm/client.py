"""Thin wrapper over litellm so the rest of the codebase is provider-agnostic.

Model strings are LiteLLM-style (e.g. "deepseek/deepseek-chat", "anthropic/claude-opus-4-8").
Tool calling uses the OpenAI tool schema, which LiteLLM normalizes across providers.
"""

from __future__ import annotations

from typing import Any


class LLMClient:
    def __init__(self, model: str):
        self.model = model

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> Any:
        """Single completion. Returns the LiteLLM response object.

        Imported lazily so importing OptionPilot doesn't require litellm at module load.
        """
        import litellm

        return litellm.completion(
            model=self.model,
            messages=messages,
            tools=tools,
            temperature=temperature,
            **kwargs,
        )

    async def acomplete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> Any:
        import litellm

        return await litellm.acompletion(
            model=self.model,
            messages=messages,
            tools=tools,
            temperature=temperature,
            **kwargs,
        )
