"""Backtest engine: turn buy-point probabilities into a position series and P&L.

Phase 1 keeps it simple: threshold the (nudged) probability into long/flat positions on the
underlying as a proxy, apply transaction costs, and produce a per-period return series that
metrics.summarize() consumes. Option-level P&L (using OPRA quotes + computed greeks) is the
Phase 2 upgrade.

TODO: implement run() once features + model + nudge are wired.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from optionpilot.backtest.metrics import summarize


@dataclass
class BacktestResult:
    returns: np.ndarray
    metrics: dict
    meta: dict


class BacktestEngine:
    def __init__(self, threshold: float = 0.5, cost_bps: float = 1.0):
        self.threshold = threshold
        self.cost_bps = cost_bps  # round-trip transaction cost in basis points

    def run(self, probabilities: np.ndarray, market: pd.DataFrame, meta: dict | None = None
            ) -> BacktestResult:
        """probabilities aligned to market rows; market has at least an underlying return col.

        TODO: positions = (prob > threshold); returns = positions.shift * underlying_ret - costs
        """
        raise NotImplementedError("BacktestEngine.run")
