"""Planner: proposes the next experiment instead of blindly tweaking parameters.

This is what makes OptionPilot an *intern* rather than a one-shot tool: after each backtest
it looks at the metrics so far and proposes a concrete next experiment (new feature, a rule
change, a hyperparameter change), with a rationale. Phase 1 surfaces the proposal for human
approval; Phase 2 lets the loop act on it automatically.

TODO(phase2): implement LLM-driven hypothesis generation over the ExperimentTracker history.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExperimentProposal:
    hypothesis: str
    change: str  # concrete change to apply (feature / rule / hyperparam)
    rationale: str


class Planner:
    def __init__(self, llm=None):
        self.llm = llm

    def propose_next(self, history: list[dict]) -> ExperimentProposal:
        """Given past run configs+metrics, propose the next experiment."""
        raise NotImplementedError("Planner.propose_next — implement in Phase 2")
