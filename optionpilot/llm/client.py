"""Thin wrapper over litellm so the rest of the codebase is provider-agnostic.

Model strings are LiteLLM-style (e.g. "deepseek/deepseek-v4-flash", "anthropic/claude-opus-4-8").
For a local OpenAI-compatible server (vLLM / Ollama / LM Studio), set api_base and use a
"hosted_vllm/<served-name>" (or "openai/<served-name>") model string.
Tool calling uses the OpenAI tool schema, which LiteLLM normalizes across providers.
"""

from __future__ import annotations

from typing import Any

from optionpilot.config import Config


class LLMClient:
    def __init__(self, model: str, api_base: str | None = None, api_key: str | None = None):
        self.model = model
        self.api_base = api_base
        self.api_key = api_key

    @classmethod
    def from_config(cls, config: Config) -> "LLMClient":
        return cls(model=config.model, api_base=config.api_base, api_key=config.api_key)

    def _extra(self) -> dict[str, Any]:
        extra: dict[str, Any] = {}
        if self.api_base:
            extra["api_base"] = self.api_base
            # local servers ignore the key but litellm wants something non-empty
            extra["api_key"] = self.api_key or "local"
        elif self.api_key:
            extra["api_key"] = self.api_key
        return extra

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
            **self._extra(),
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
            **self._extra(),
            **kwargs,
        )
