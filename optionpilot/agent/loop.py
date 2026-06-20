"""ExperimentLoop: the agentic loop, specialized for options-strategy research.

Borrowed structure from ml-intern's submission loop:
    1. invoke LLM (litellm) with the current context + tool schemas
    2. parse tool calls from the response
    3. approval-gate sensitive calls, then dispatch via ToolRouter
    4. record results into context; doom-loop detector guards against repetition
    5. repeat up to max_iterations until the LLM emits no more tool calls

Wiring of LLM tool-call parsing is the next implementation milestone (after the data layer);
the skeleton below fixes the interface so tools and the router can be built against it.
"""

from __future__ import annotations

from optionpilot.agent.context import ContextManager
from optionpilot.agent.doom_loop import DoomLoopDetector
from optionpilot.agent.router import ToolRouter
from optionpilot.config import Config
from optionpilot.llm import LLMClient

SYSTEM_PROMPT = (
    "You are OptionPilot, an autonomous options-strategy research agent — an ML intern for "
    "options. You research buy-point strategies by fetching data, engineering features, "
    "training a baseline model with an optional Nudge layer, backtesting, and running "
    "ablations. You validate every signal with backtest metrics (Sharpe, max drawdown, win "
    "rate) rather than asserting it works. Use the provided tools; never fabricate data."
)


class ExperimentLoop:
    def __init__(self, config: Config, router: ToolRouter, llm: LLMClient | None = None):
        self.config = config
        self.router = router
        self.llm = llm or LLMClient(config.model)
        self.context = ContextManager(compact_at_tokens=config.context_compact_tokens)
        self.doom = DoomLoopDetector()
        self.context.add("system", SYSTEM_PROMPT)

    def run(self, task: str) -> str:
        """Run the loop for a single user task and return the final assistant message.

        TODO(next): implement the iterate-until-no-tool-calls loop:
          - call self.llm.complete(messages, tools=self.router.openai_schemas())
          - parse tool_calls; for each, self.router.dispatch(name, args)
          - feed doom-loop corrections; compact context when needed
        """
        self.context.add("user", task)
        raise NotImplementedError("ExperimentLoop.run — implement after the data layer lands")
