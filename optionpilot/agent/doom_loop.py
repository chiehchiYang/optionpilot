"""Doom-loop detector: spot the agent repeating the same tool call and nudge it out of it.

Borrowed from ml-intern. If the same (tool_name, args) signature repeats N times within a
sliding window, `check` returns a corrective message to inject into the conversation.
"""

from __future__ import annotations

import json
from collections import deque
from typing import Any


class DoomLoopDetector:
    def __init__(self, window: int = 6, threshold: int = 3):
        self.window = window
        self.threshold = threshold
        self._recent: deque[str] = deque(maxlen=window)

    @staticmethod
    def _sig(name: str, args: dict[str, Any]) -> str:
        return f"{name}:{json.dumps(args, sort_keys=True, default=str)}"

    def record(self, name: str, args: dict[str, Any]) -> str | None:
        """Record a call; return a corrective prompt if a loop is detected, else None."""
        sig = self._sig(name, args)
        self._recent.append(sig)
        if self._recent.count(sig) >= self.threshold:
            self._recent.clear()
            return (
                f"You have called `{name}` with identical arguments "
                f"{self.threshold} times with no new result. Stop repeating it. "
                "Re-read the previous results, change your approach, or report what is "
                "blocking you instead of retrying the same call."
            )
        return None
