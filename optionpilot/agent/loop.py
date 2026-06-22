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
from optionpilot.agent.lang import to_traditional
from optionpilot.agent.planner import Planner
from optionpilot.agent.playbook import RESEARCH_PLAYBOOK
from optionpilot.agent.router import ToolRouter
from optionpilot.agent.trajectory import Trajectory
from optionpilot.config import Config
from optionpilot.llm import LLMClient

OPTIONS_SYSTEM_PROMPT = (
    "You are OptionPilot, an autonomous options-strategy research agent — an ML intern for "
    "options. You research defined-risk option-selling strategies (e.g. cash-secured puts) by "
    "running real backtests on historical option chains and screening for unusual options "
    "activity.\n"
    "SCOPE: you do options-strategy research with your tools (variance-risk-premium screening, "
    "cash-secured-put / covered-call / wheel backtests, walk-forward validation, unusual options "
    "activity) and you can generate charts with make_charts (price trend, strategy equity vs "
    "buy&hold, IV vs realized vol, option volume + put/call ratio). When the user asks to see a "
    "chart/trend/visualization, call make_charts. The charts are shown automatically in the UI — "
    "do NOT write your own markdown image links. If make_charts returns any 'skipped' charts, "
    "tell the user which were skipped and the reason. For support/resistance, call support_resistance "
    "and explain it FAITHFULLY from the result: support_levels are recent swing lows BELOW the "
    "current price ordered nearest-to-furthest (NOT by time), resistance_levels are swing highs "
    "ABOVE ordered nearest-to-furthest, pivots are classic levels — never invent time-based or "
    "predictive meanings. You do NOT predict prices or give news. If a request is out of scope, "
    "say so in one sentence and name what you CAN do — do NOT call ask_user.\n"
    "Workflow rules:\n"
    "1. CONFIRM FIRST only when an ESSENTIAL input is missing — i.e. no ticker, or no date "
    "range. Methodology choices (fixed params vs a parameter sweep, which strategy variant, "
    "DTE/moneyness) are YOURS to decide per the playbook — never ask the user about those. If "
    "the ticker and dates are given, proceed immediately without calling ask_user.\n"
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
    "6. LANGUAGE: match the user's language. For ANY Chinese you MUST write in Traditional "
    "Chinese (繁體中文/正體字) ONLY — never Simplified (简体字). Use 體/與/數據/這/個/沒/會, "
    "never 体/与/数据/这/个/没/会.\n"
    "7. CAPABILITIES: if the user asks what you can do or which tools you have, list the tools "
    "from 'Your tools' below with a one-line description each — no tool call needed.\n"
    "Use the provided tools; never fabricate data or metrics."
)

CRYPTO_SYSTEM_PROMPT = (
    "You are OptionPilot — Perp Desk, an autonomous research agent for Binance USDⓈ-M PERPETUAL "
    "FUTURES (永續合約). The perps include crypto (BTCUSDT…) AND US-stock perps like NOKUSDT / "
    "AAPLUSDT / TSLAUSDT / SPYUSDT. You use PUBLIC market data only — no API key, no order "
    "placement; you analyze and backtest, you do NOT trade.\n"
    "SCOPE: with your tools you (a) analyze the funding-rate carry — funding_analysis: annualized "
    "funding, who pays (longs vs shorts), the favoured carry side, vs the underlying's realized "
    "vol — which is the perp analog of the options variance risk premium; and (b) backtest a GRID "
    "bot — grid_backtest: booked grid profit vs stuck-inventory unrealized loss, time spent "
    "outside the grid, fee + funding drag, all benchmarked against buy&hold. You do NOT do stock "
    "OPTIONS here, you do NOT predict prices, and you give no news. If a request is out of scope, "
    "say so in one sentence and name what you CAN do — do NOT call ask_user.\n"
    "Workflow rules:\n"
    "1. CONFIRM FIRST only when an ESSENTIAL input is missing — i.e. no symbol. Methodology "
    "choices (interval, n_grids, grid range, how many bars) are YOURS to decide per the playbook "
    "— never ask the user about those. If the symbol is given, proceed immediately.\n"
    "2. Always read carry/grid results HONESTLY against the alternative of simply buying & "
    "holding. A fat annualized funding is not free money (check pct_intervals_positive and the "
    "underlying's realized vol); a grid that books profit can still be deep underwater on stuck "
    "inventory in a downtrend (check open_unrealized_pnl and pct_time_below_lower).\n"
    "3. DATES: you have no clock — use the current date given below. Convert relative ranges into "
    "absolute ISO dates yourself.\n"
    "4. LANGUAGE: match the user's language. For ANY Chinese you MUST write in Traditional "
    "Chinese (繁體中文/正體字) ONLY — never Simplified (简体字). Use 體/與/數據/這/個/沒/會, "
    "never 体/与/数据/这/个/没/会.\n"
    "5. CAPABILITIES: if the user asks what you can do or which tools you have, list the tools "
    "from 'Your tools' below with a one-line description each — no tool call needed.\n"
    "Use the provided tools; never fabricate data or metrics."
)


def _tools_section(router) -> str:
    lines = []
    for s in router.specs():
        desc = s.description.split(". ")[0].rstrip(".")
        lines.append(f"- {s.name}: {desc}.")
    return "Your tools:\n" + "\n".join(lines)


def _system_prompt(today: str, router=None, base_prompt: str = OPTIONS_SYSTEM_PROMPT,
                   playbook: str = RESEARCH_PLAYBOOK) -> str:
    tools = f"\n\n{_tools_section(router)}" if router is not None else ""
    return f"{base_prompt}\n\nThe current date is {today}.\n\n{playbook}{tools}"


class ExperimentLoop:
    def __init__(
        self,
        config: Config,
        router: ToolRouter,
        llm: LLMClient | None = None,
        on_event: Callable[[str, str], None] | None = None,
        system_prompt: str = OPTIONS_SYSTEM_PROMPT,
        playbook: str = RESEARCH_PLAYBOOK,
        profile_key: str = "options",
        persist_trajectory: bool = True,
    ):
        self.config = config
        self.router = router
        self.llm = llm or LLMClient.from_config(config)
        self.context = ContextManager(compact_at_tokens=config.context_compact_tokens)
        self.doom = DoomLoopDetector()
        self.planner = Planner(self.llm)
        self.profile_key = profile_key
        self.persist_trajectory = persist_trajectory
        self.trajectory: Trajectory | None = None  # set per run()/run_planned()
        # on_event(kind, text): surfaces tool activity to the UI; defaults to stderr.
        self.on_event = on_event or self._default_event
        self.context.add("system", _system_prompt(date.today().isoformat(), router,
                                                   system_prompt, playbook))

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
        """Run the reactive tool-calling loop for one task; record + persist the trajectory."""
        self.trajectory = Trajectory(task, self.profile_key)
        self.trajectory.add("task", task)
        text = self._react(task)
        self.trajectory.verdict(text)
        self._persist_trajectory()
        return to_traditional(text)

    def run_planned(self, task: str, max_rounds: int = 4) -> str:
        """Planner-driven research: each round the Planner proposes an explicit hypothesis +
        change (a recorded node), the reactive loop executes it, then we synthesize a verdict.

        This makes the research PATH explicit and structured — every step's hypothesis and
        decision is a node in the trajectory — instead of being implicit in the tool loop."""
        self.trajectory = Trajectory(task, self.profile_key)
        self.trajectory.add("task", task)
        history: list[dict] = []
        for r in range(max_rounds):
            proposal = self.planner.propose_next(task, history)
            self.trajectory.plan(proposal.hypothesis, proposal.change, proposal.rationale,
                                 proposal.done)
            self.on_event("plan", f"R{r + 1}: {proposal.change or '(judged: done)'}")
            if proposal.done:
                break
            directive = (f"研究假設:{proposal.hypothesis}\n下一步請執行:{proposal.change}\n"
                         "用你的工具實際驗證,並讀出關鍵指標(務必對比 buy&hold)。")
            result = self._react(directive)
            history.append({"hypothesis": proposal.hypothesis, "change": proposal.change,
                            "result": result[:800]})
        verdict = self._react("根據以上所有實驗,寫出誠實的最終結論:證據強弱、是否優於買進持有、"
                              "有哪些限制。不要誇大。")
        self.trajectory.verdict(verdict)
        self._persist_trajectory()
        return to_traditional(verdict)

    def _react(self, task: str) -> str:
        """The reactive tool-calling loop: feed a directive, run tools until the LLM answers.

        Records each step into self.trajectory (decision = the assistant's stated reasoning;
        tool = name/args/result). Returns the final assistant text (untranslated)."""
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
                return last_text  # no more tools -> final answer for this directive

            if last_text and self.trajectory is not None:
                self.trajectory.decision(last_text)  # the agent's reasoning before acting

            for tc in tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError as e:
                    result = f"ERROR: arguments for '{name}' were not valid JSON: {e}"
                    self.on_event("tool-error", f"{name}: bad JSON args")
                    if self.trajectory is not None:
                        self.trajectory.tool(name, tc.function.arguments, result)
                    self._add_tool_result(tc.id, result)
                    continue

                correction = self.doom.record(name, args)
                if correction:
                    self.on_event("doom-loop", f"{name} repeated; injecting correction")
                    self._add_tool_result(tc.id, f"BLOCKED (loop detected): {correction}")
                    continue

                arg_str = json.dumps(args, ensure_ascii=False, default=str)  # keep CJK readable
                if len(arg_str) > 120:
                    arg_str = arg_str[:117] + "…"
                self.on_event("tool", f"{name}({arg_str})")
                result = self.router.dispatch(name, args)
                if self.trajectory is not None:
                    self.trajectory.tool(name, args, result)
                self._add_tool_result(tc.id, result)

        return last_text or "(stopped: reached max iterations without a final answer)"

    def _persist_trajectory(self) -> None:
        """Save the run's path to runs/trajectories/ (best-effort; never crash the run)."""
        if not self.persist_trajectory or self.trajectory is None:
            return
        try:
            self.config.ensure_dirs()
            paths = self.trajectory.save(self.config.runs_dir / "trajectories")
            self.on_event("trajectory", f"研究路徑已存:{paths['md']}")
        except Exception as e:  # noqa: BLE001 - persistence must never break the run
            self.on_event("trajectory-error", str(e))

    def _add_tool_result(self, tool_call_id: str, content: str) -> None:
        self.context.add_raw({"role": "tool", "tool_call_id": tool_call_id, "content": content})
