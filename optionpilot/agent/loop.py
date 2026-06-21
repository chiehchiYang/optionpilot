"""ExperimentLoop: the agentic loop, specialized for options-strategy research.

Borrowed structure from ml-intern's submission loop:
    1. invoke LLM (litellm) with the current context + tool schemas
    2. parse tool calls from the response
    3. approval-gate sensitive calls (via ToolRouter), then dispatch
    4. record results into context; doom-loop detector guards against repetition
    5. repeat up to max_iterations until the LLM emits no more tool calls
"""

from __future__ import annotations

import json
import sys
from datetime import date
from typing import Any, Callable

from optionpilot.agent.context import ContextManager
from optionpilot.agent.doom_loop import DoomLoopDetector
from optionpilot.agent.router import ToolRouter
from optionpilot.config import Config
from optionpilot.llm import LLMClient

SYSTEM_PROMPT = (
    "You are OptionPilot, an autonomous options-strategy research agent — an ML intern for "
    "options. You research defined-risk option-selling strategies (e.g. cash-secured puts) by "
    "running real backtests on historical option chains and screening for unusual options "
    "activity.\n"
    "Workflow rules:\n"
    "1. CONFIRM FIRST: if the request is underspecified (missing ticker, date range, or whether "
    "to use fixed params vs a sweep), call ask_user to clarify BEFORE running anything. Do not "
    "silently guess key choices.\n"
    "2. Fetching new option data costs money and is approval-gated — the user is prompted; if a "
    "fetch is denied, say so and stop rather than working around it.\n"
    "3. Always judge a strategy against its buy-and-hold benchmark: a high win rate means little "
    "if the strategy trails simply owning the stock. Report drawdowns, assignment rate, and "
    "underperformance honestly. A high implied vol is NOT automatically good to sell — use "
    "measure_vrp to check IV vs DOWNSIDE realized vol, and note if the stock rocketed (then "
    "owning it beats selling puts).\n"
    "4. run_backtest auto-saves a Markdown report and logs the run; tell the user the report path.\n"
    "5. DATES: you have no clock — use the current date given below. Convert relative ranges "
    "(e.g. 'last two years', 'two years back from today') into absolute ISO dates yourself. "
    "Option data only exists up to roughly yesterday, so never use a future end date.\n"
    "Use the provided tools; never fabricate data or metrics."
)


def _system_prompt(today: str) -> str:
    return f"{SYSTEM_PROMPT}\n\nThe current date is {today}."


class ExperimentLoop:
    def __init__(
        self,
        config: Config,
        router: ToolRouter,
        llm: LLMClient | None = None,
        on_event: Callable[[str, str], None] | None = None,
    ):
        self.config = config
        self.router = router
        self.llm = llm or LLMClient.from_config(config)
        self.context = ContextManager(compact_at_tokens=config.context_compact_tokens)
        self.doom = DoomLoopDetector()
        # on_event(kind, text): surfaces tool activity to the UI; defaults to stderr.
        self.on_event = on_event or self._default_event
        self.context.add("system", _system_prompt(date.today().isoformat()))

    @staticmethod
    def _default_event(kind: str, text: str) -> None:
        print(f"  [{kind}] {text}", file=sys.stderr)

    def _summarize(self, messages: list[dict[str, Any]]) -> str:
        """Summarize older turns for context compaction (best-effort LLM call)."""
        try:
            joined = "\n".join(f"{m.get('role')}: {str(m.get('content'))[:500]}" for m in messages)
            resp = self.llm.complete(
                messages=[
                    {"role": "system", "content": "Summarize this agent transcript tersely, "
                     "preserving decisions, tool results, and metrics."},
                    {"role": "user", "content": joined},
                ],
                temperature=0,
            )
            return resp.choices[0].message.content or "(summary unavailable)"
        except Exception:  # noqa: BLE001 - compaction must never crash the loop
            return "(earlier context omitted)"

    @staticmethod
    def _assistant_dict(msg: Any) -> dict[str, Any]:
        """Convert a LiteLLM response message into a plain dict for the transcript."""
        out: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
        if getattr(msg, "tool_calls", None):
            out["tool_calls"] = [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ]
        return out

    def run(self, task: str) -> str:
        """Run the loop for a single user task and return the final assistant message."""
        self.context.add("user", task)
        schemas = self.router.openai_schemas()

        last_text = ""
        for _ in range(self.config.max_iterations):
            if self.context.needs_compaction():
                self.context.compact(self._summarize)

            resp = self.llm.complete(messages=self.context.messages, tools=schemas)
            msg = resp.choices[0].message
            self.context.add_raw(self._assistant_dict(msg))
            last_text = (msg.content or "").strip()

            tool_calls = getattr(msg, "tool_calls", None)
            if not tool_calls:
                return last_text  # no more tools -> final answer

            for tc in tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError as e:
                    result = f"ERROR: arguments for '{name}' were not valid JSON: {e}"
                    self.on_event("tool-error", f"{name}: bad JSON args")
                    self._add_tool_result(tc.id, result)
                    continue

                correction = self.doom.record(name, args)
                if correction:
                    self.on_event("doom-loop", f"{name} repeated; injecting correction")
                    self._add_tool_result(tc.id, f"BLOCKED (loop detected): {correction}")
                    continue

                self.on_event("tool", f"{name}({json.dumps(args, default=str)})")
                result = self.router.dispatch(name, args)
                self._add_tool_result(tc.id, result)

        return last_text or "(stopped: reached max iterations without a final answer)"

    def _add_tool_result(self, tool_call_id: str, content: str) -> None:
        self.context.add_raw({"role": "tool", "tool_call_id": tool_call_id, "content": content})
