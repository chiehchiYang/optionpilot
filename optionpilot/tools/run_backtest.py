"""Tool: run_backtest — self-contained cash-secured-put backtest with a buy&hold benchmark.

The agent calls this with a ticker + date range; the tool loads the option chain (cached
Databento) and the underlying (yfinance), runs the backtest, and returns compact metrics —
including the buy-and-hold benchmark so a good win-rate can't hide underperformance.
"""

from __future__ import annotations

from optionpilot.backtest.strategies import CSPParams, cash_secured_put_backtest
from optionpilot.config import Config
from optionpilot.data.market import load_option_chain, load_underlying
from optionpilot.tools.base import ToolSpec

PARAMETERS = {
    "type": "object",
    "properties": {
        "ticker": {"type": "string", "description": "Underlying ticker, e.g. ZETA"},
        "start": {"type": "string", "description": "ISO date, e.g. 2023-01-01"},
        "end": {"type": "string", "description": "ISO date, e.g. 2025-01-01"},
        "strategy": {"type": "string", "enum": ["cash_secured_put"],
                     "default": "cash_secured_put"},
        "target_moneyness": {"type": "number", "default": 0.95,
                             "description": "Sell put strike ~ this fraction of spot (OTM)."},
        "dte_min": {"type": "integer", "default": 25},
        "dte_max": {"type": "integer", "default": 45},
    },
    "required": ["ticker", "start", "end"],
}


def build(config: Config) -> ToolSpec:
    def handler(ticker, start, end, strategy="cash_secured_put",
                target_moneyness=0.95, dte_min=25, dte_max=45):
        if strategy != "cash_secured_put":
            return {"error": f"unsupported strategy: {strategy}"}
        opt = load_option_chain(config, ticker, start, end)
        under = load_underlying(ticker, start, end)
        params = CSPParams(target_moneyness=target_moneyness, dte_min=dte_min, dte_max=dte_max)
        res = cash_secured_put_backtest(opt, under, params)
        if not res.metrics:
            return {"ticker": ticker, "n_trades": 0, "note": "no trades generated for these params"}
        m = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in res.metrics.items()}
        m["ticker"] = ticker.upper()
        m["strategy"] = strategy
        return m

    return ToolSpec(
        name="run_backtest",
        description="Backtest a defined-risk option-selling strategy (cash-secured puts) on a "
                    "ticker over a date range. Returns Sharpe, max drawdown, win rate, assigned "
                    "rate, total return, AND a buy-and-hold benchmark + excess-vs-benchmark.",
        parameters=PARAMETERS,
        handler=handler,
        tags=["backtest"],
    )
