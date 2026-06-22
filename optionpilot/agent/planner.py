"""Planner: propose the next experiment from what's been run so far.

This is the "iterate" brain of the intern: given the research question and the experiments
already run (params + metrics), it proposes the single most informative next experiment — or
declares the research done. In the live ExperimentLoop the agent plans via its own tool-calling
loop (guided by the playbook); this Planner is the structured, testable building block for a
headless iterate-until-converged driver.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

_SYSTEM = (
    "You are the planning brain of an options-strategy research intern. Given the research "
    "question and the experiments run so far (each with params + metrics), propose the single "
    "MOST INFORMATIVE next experiment, or declare done if there is already enough evidence for "
    "an honest answer. Prefer experiments that change one thing (DTE window, moneyness, "
    "cash_secured_put vs covered_call) and that would most change the conclusion. Respond with "
    'ONLY a JSON object: {"done": bool, "hypothesis": str, "change": str, "rationale": str}.'
)


@dataclass
class ExperimentProposal:
    done: bool
    hypothesis: str
    change: str       # concrete change to apply next (one knob)
    rationale: str


def _extract_json(text: str) -> str:
    t = text.strip()
    if "```" in t:  # strip code fences
        t = t.split("```")[1].removeprefix("json").strip() if t.count("```") >= 2 else t
    start, end = t.find("{"), t.rfind("}")
    return t[start:end + 1] if start != -1 and end != -1 else t


class Planner:
    def __init__(self, llm):
        self.llm = llm

    def propose_next(self, question: str, history: list[dict]) -> ExperimentProposal:
        user = (f"Question: {question}\n\nExperiments so far:\n"
                f"{json.dumps(history, indent=2, default=str)}")
        resp = self.llm.complete(
            messages=[{"role": "system", "content": _SYSTEM},
                      {"role": "user", "content": user}],
            temperature=0,
        )
        text = resp.choices[0].message.content or "{}"
        try:
            data = json.loads(_extract_json(text))
        except (json.JSONDecodeError, ValueError):
            data = {"done": False, "hypothesis": "", "change": "(unparseable planner output)",
                    "rationale": text[:200]}
        return ExperimentProposal(
            done=bool(data.get("done", False)),
            hypothesis=str(data.get("hypothesis", "")),
            change=str(data.get("change", "")),
            rationale=str(data.get("rationale", "")),
        )
