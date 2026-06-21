"""Tool: optimize_strategy — walk-forward tuning of the cash-secured-put strategy.

Sweeps strike/DTE on an in-sample window, picks the best, then reports its OUT-OF-SAMPLE
result so the user sees whether the tuning held up (anti-overfitting).
"""

from __future__ import annotations

from optionpilot.backtest.walkforward import walk_forward_csp
from optionpilot.config import Config
from optionpilot.data.market import load_option_chain, load_underlying
from optionpilot.tools.base import ToolSpec

PARAMETERS = {
    "type": "object",
    "properties": {
        "ticker": {"type": "string"},
        "start": {"type": "string"},
        "end": {"type": "string"},
        "split_frac": {"type": "number", "default": 0.5,
                       "description": "Fraction of the period used as in-sample (train)."},
        "objective": {"type": "string", "default": "total_return",
                      "enum": ["total_return", "sharpe_annualized", "excess_vs_buy_hold",
                               "win_rate"],
                      "description": "Metric maximized in-sample to pick the best parameters."},
        "min_contract_volume": {"type": "integer", "default": 10},
    },
    "required": ["ticker", "start", "end"],
}


def _slim(m: dict) -> dict:
    keys = ("n_trades", "total_return", "excess_vs_buy_hold", "sharpe_annualized",
            "win_rate", "max_drawdown", "benchmark_buy_hold")
    return {k: (round(m[k], 4) if isinstance(m.get(k), float) else m.get(k))
            for k in keys if k in m}


def build(config: Config, approve_spend=None) -> ToolSpec:
    def handler(ticker, start, end, split_frac=0.5, objective="total_return",
                min_contract_volume=10):
        from optionpilot.data.databento_fetcher import CostGuardError, FetchDenied
        try:
            opt = load_option_chain(config, ticker, start, end, approve=approve_spend)
        except (FetchDenied, CostGuardError) as e:
            return {"ticker": ticker.upper(), "ran": False, "reason": str(e)}
        under = load_underlying(ticker, start, end)
        res = walk_forward_csp(opt, under, split_frac=split_frac, objective=objective,
                               base={"min_contract_volume": min_contract_volume})
        if "error" in res:
            return {"ticker": ticker.upper(), **res}
        return {
            "ticker": ticker.upper(),
            "split_date": res["split_date"],
            "objective": objective,
            "best_params": res["best_params"],
            "in_sample": _slim(res["in_sample"]),
            "out_of_sample": _slim(res["out_of_sample"]),
        }

    return ToolSpec(
        name="optimize_strategy",
        description="Walk-forward tune the cash-secured-put strategy: sweep strike/DTE on an "
                    "in-sample window, pick the best by the objective, then report its "
                    "out-of-sample result. Use this instead of reporting the best full-history "
                    "backtest — it exposes overfitting (out-of-sample much worse than in-sample).",
        parameters=PARAMETERS,
        handler=handler,
        tags=["backtest"],
    )
