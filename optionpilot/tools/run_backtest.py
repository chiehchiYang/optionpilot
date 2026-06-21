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
from optionpilot.tracking import ExperimentTracker
from optionpilot.tracking.report import write_backtest_report

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
        "min_contract_volume": {"type": "integer", "default": 10,
                                "description": "Only enter contracts with >= this day's volume "
                                "(filters unfillable thinly-traded contracts; honest default)."},
        "risk_free_rate": {"type": "number", "default": 0.0,
                           "description": "Annual rate earned on cash collateral, e.g. 0.05; "
                           "0 ignores it (understates a cash-secured put's real return)."},
        "entry_every_days": {"type": "integer", "default": 0,
                             "description": "0 = sequential non-overlapping (clean metrics, "
                             "default). >0 opens a new position every N trading days (overlapping "
                             "sampling, ~5=weekly) for more trades on short histories — but the "
                             "annualized Sharpe becomes inflated/unreliable under overlap."},
    },
    "required": ["ticker", "start", "end"],
}


def build(config: Config, approve_spend=None) -> ToolSpec:
    def handler(ticker, start, end, strategy="cash_secured_put",
                target_moneyness=0.95, dte_min=25, dte_max=45,
                min_contract_volume=10, risk_free_rate=0.0, entry_every_days=0):
        if strategy != "cash_secured_put":
            return {"error": f"unsupported strategy: {strategy}"}
        from optionpilot.data.databento_fetcher import CostGuardError, FetchDenied
        try:
            opt = load_option_chain(config, ticker, start, end, approve=approve_spend)
        except (FetchDenied, CostGuardError) as e:
            return {"ticker": ticker.upper(), "ran": False, "reason": str(e)}
        under = load_underlying(ticker, start, end)
        params = CSPParams(target_moneyness=target_moneyness, dte_min=dte_min, dte_max=dte_max,
                           min_contract_volume=min_contract_volume, risk_free_rate=risk_free_rate,
                           entry_every_days=entry_every_days)
        res = cash_secured_put_backtest(opt, under, params)
        if not res.metrics:
            return {"ticker": ticker, "n_trades": 0, "note": "no trades generated for these params"}
        m = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in res.metrics.items()}
        m["ticker"] = ticker.upper()
        m["strategy"] = strategy

        # auto-save: log to the experiment DB + write a Markdown report under runs/
        run_params = {"target_moneyness": target_moneyness, "dte_min": dte_min,
                      "dte_max": dte_max, "min_contract_volume": min_contract_volume,
                      "risk_free_rate": risk_free_rate, "entry_every_days": entry_every_days,
                      "start": start, "end": end}
        config.ensure_dirs()
        tracker = ExperimentTracker(config.runs_dir / "experiments.duckdb")
        run_id = tracker.log_run(ticker, strategy, run_params, res.metrics)
        report = write_backtest_report(config.runs_dir, ticker, strategy, run_params,
                                       res.metrics, res.trades, run_id, start, end)
        m["run_id"] = run_id
        m["report_path"] = str(report)
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
