"""NudgeLayer: post-processing rule-reweight on top of the model's buy probability.

Core differentiator. The model emits p_model in [0,1]; each NudgeRule inspects the feature
row and returns a signed adjustment; the layer sums weighted adjustments and clips:

    p_final = clip( p_model + Σ wᵢ · ruleᵢ(features),  0, 1 )

Because the layer is a pluggable wrapper, the agent can run ablation trivially: backtest with
`NudgeLayer(rules)` vs the raw model and compare metrics. Set enabled=False to bypass.

Example rule (oversold boost):
    NudgeRule("rsi_oversold", lambda f: 1.0 if f["rsi"] < 30 else 0.0, weight=0.1)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping

import numpy as np

Features = Mapping[str, float]


@dataclass
class NudgeRule:
    name: str
    fn: Callable[[Features], float]  # returns a signal in roughly [-1, 1]
    weight: float = 0.1

    def adjustment(self, features: Features) -> float:
        return self.weight * float(self.fn(features))


@dataclass
class NudgeLayer:
    rules: list[NudgeRule] = field(default_factory=list)
    enabled: bool = True

    def apply_one(self, p_model: float, features: Features) -> float:
        if not self.enabled or not self.rules:
            return float(np.clip(p_model, 0.0, 1.0))
        delta = sum(r.adjustment(features) for r in self.rules)
        return float(np.clip(p_model + delta, 0.0, 1.0))

    def apply(self, p_model: np.ndarray, feature_rows: list[Features]) -> np.ndarray:
        """Vectorized over a batch of (probability, feature-row) pairs."""
        if len(p_model) != len(feature_rows):
            raise ValueError("p_model and feature_rows length mismatch")
        return np.array(
            [self.apply_one(p, f) for p, f in zip(p_model, feature_rows)], dtype=float
        )

    def describe(self) -> list[dict]:
        """For the ablation report: which rules and weights were active."""
        return [{"name": r.name, "weight": r.weight} for r in self.rules]
