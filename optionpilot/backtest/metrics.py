"""Performance metrics for a strategy's return series.

Returns are per-period simple returns (e.g. daily). These are the numbers the agent reports
and the planner reasons over when deciding the next experiment.
"""

from __future__ import annotations

import numpy as np

TRADING_DAYS = 252


def sharpe_ratio(returns: np.ndarray, rf: float = 0.0, periods: int = TRADING_DAYS) -> float:
    r = np.asarray(returns, dtype=float)
    if r.size < 2:
        return 0.0
    excess = r - rf / periods
    sd = excess.std(ddof=1)
    if sd == 0:
        return 0.0
    return float(np.sqrt(periods) * excess.mean() / sd)


def max_drawdown(returns: np.ndarray) -> float:
    """Largest peak-to-trough decline of the cumulative equity curve (negative number)."""
    r = np.asarray(returns, dtype=float)
    if r.size == 0:
        return 0.0
    equity = np.cumprod(1.0 + r)
    peak = np.maximum.accumulate(equity)
    drawdown = equity / peak - 1.0
    return float(drawdown.min())


def win_rate(returns: np.ndarray) -> float:
    r = np.asarray(returns, dtype=float)
    nonzero = r[r != 0]
    if nonzero.size == 0:
        return 0.0
    return float((nonzero > 0).mean())


def summarize(returns: np.ndarray, turnover: float | None = None) -> dict[str, float]:
    r = np.asarray(returns, dtype=float)
    out = {
        "sharpe": sharpe_ratio(r),
        "max_drawdown": max_drawdown(r),
        "win_rate": win_rate(r),
        "total_return": float(np.prod(1.0 + r) - 1.0) if r.size else 0.0,
        "n_periods": int(r.size),
    }
    if turnover is not None:
        out["turnover"] = float(turnover)
    return out
