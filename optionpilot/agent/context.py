"""ContextManager: holds message history and compacts it when it grows too large.

Borrowed from ml-intern: when the estimated token count crosses a threshold (default 170k),
older turns are summarized into a single compacted system message, preserving the head
(system prompt + task) and the most recent turns verbatim.
"""

from __future__ import annotations

from typing import Any, Callable


def _estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """Cheap heuristic: ~4 chars per token over serialized content."""
    chars = sum(len(str(m.get("content", ""))) for m in messages)
    return chars // 4


class ContextManager:
    def __init__(self, compact_at_tokens: int = 170_000, keep_recent: int = 6):
        self.messages: list[dict[str, Any]] = []
        self.compact_at_tokens = compact_at_tokens
        self.keep_recent = keep_recent

    def add(self, role: str, content: str, **extra: Any) -> None:
        self.messages.append({"role": role, "content": content, **extra})

    def add_raw(self, message: dict[str, Any]) -> None:
        self.messages.append(message)

    def token_estimate(self) -> int:
        return _estimate_tokens(self.messages)

    def needs_compaction(self) -> bool:
        return self.token_estimate() >= self.compact_at_tokens

    def compact(self, summarize: Callable[[list[dict[str, Any]]], str]) -> None:
        """Replace the middle of the history with a summary.

        Keeps message[0] (system) and the last `keep_recent` messages; everything between
        is handed to `summarize` (typically an LLM call) and replaced by one system note.
        """
        if len(self.messages) <= self.keep_recent + 1:
            return
        head = self.messages[:1]
        tail = self.messages[-self.keep_recent :]
        middle = self.messages[1 : -self.keep_recent]
        summary = summarize(middle)
        self.messages = head + [
            {"role": "system", "content": f"[compacted earlier context]\n{summary}"}
        ] + tail
