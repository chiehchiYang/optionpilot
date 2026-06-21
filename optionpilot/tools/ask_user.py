"""Tool: ask_user — clarify an underspecified request before doing real work.

The agent calls this when key details are missing (ticker, date range, strategy params) so it
confirms intent instead of guessing. With no interactive terminal (headless/piped), it returns
a note telling the agent to proceed with sensible defaults and state its assumptions.
"""

from __future__ import annotations

import sys

from optionpilot.config import Config
from optionpilot.tools.base import ToolSpec

PARAMETERS = {
    "type": "object",
    "properties": {
        "question": {"type": "string",
                     "description": "The clarifying question to ask the user."},
    },
    "required": ["question"],
}


def build(config: Config, approve_spend=None) -> ToolSpec:
    def handler(question):
        if not sys.stdin.isatty():
            return ("NO_INTERACTIVE_TERMINAL: proceed with sensible defaults and state your "
                    "assumptions explicitly in the final answer.")
        print(f"\n❓ {question}")
        ans = input("   your answer: ").strip()
        return ans or "(no answer given; use sensible defaults and state assumptions)"

    return ToolSpec(
        name="ask_user",
        description="Ask the user a clarifying question when the request is underspecified "
                    "(missing ticker, date range, or strategy parameters). Call this BEFORE "
                    "running backtests if key details are ambiguous — confirm intent first.",
        parameters=PARAMETERS,
        handler=handler,
        tags=["interaction"],
    )
