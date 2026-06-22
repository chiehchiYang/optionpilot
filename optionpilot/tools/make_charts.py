"""Tool: make_charts — generate analysis charts (PNG) the GUI then displays.

Produces any of: price trend, strategy equity vs buy&hold, IV vs realized vol, option
volume + put/call ratio. Saved under runs/charts/; returns the file paths.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np

from optionpilot import plots
from optionpilot.analysis import implied_vol_timeseries, realized_vol
from optionpilot.backtest.strategies import (
    CSPParams,
    cash_secured_put_backtest,
    covered_call_backtest,
    wheel_backtest,
)
from optionpilot.config import Config
from optionpilot.data.market import load_option_chain, load_underlying
from optionpilot.signals import daily_put_call_ratio
from optionpilot.tools.base import ToolSpec

ALL = ["price", "equity", "iv", "volume"]
_BT = {"cash_secured_put": cash_secured_put_backtest, "covered_call": covered_call_backtest,
       "wheel": wheel_backtest}

PARAMETERS = {
    "type": "object",
    "properties": {
        "ticker": {"type": "string"},
        "start": {"type": "string"},
        "end": {"type": "string"},
        "charts": {"type": "array", "items": {"type": "string", "enum": ALL},
                   "description": "Which charts to make; omit for all four."},
        "strategy": {"type": "string",
                     "enum": ["cash_secured_put", "covered_call", "wheel"],
                     "default": "cash_secured_put"},
    },
    "required": ["ticker", "start", "end"],
}


def build(config: Config, approve_spend=None, interactive: bool = True) -> ToolSpec:
    def handler(ticker, start, end, charts=None, strategy="cash_secured_put"):
        from optionpilot.data.databento_fetcher import CostGuardError, FetchDenied
        kinds = charts or ALL
        try:
            opt = load_option_chain(config, ticker, start, end, approve=approve_spend)
        except (FetchDenied, CostGuardError) as e:
            return {"ticker": ticker.upper(), "ran": False, "reason": str(e)}
        under = load_underlying(ticker, start, end).sort_index()

        out_dir = config.runs_dir / "charts"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        tk = ticker.upper()
        paths: list[str] = []

        def p(kind):
            return out_dir / f"{tk}_{kind}_{stamp}.png"

        if "price" in kinds:
            paths.append(plots.price_trend(tk, list(under.index), list(under.values), p("price")))

        if "equity" in kinds:
            res = _BT.get(strategy, cash_secured_put_backtest)(
                opt, under, CSPParams(min_contract_volume=10))
            if res.trades:
                edates = [t["entry"] for t in res.trades]
                strat_eq = list(np.cumprod([1 + t["return"] for t in res.trades]))
                base = float(under[under.index <= edates[0]].iloc[-1])
                bh_eq = [float(under[under.index <= d].iloc[-1]) / base for d in edates]
                paths.append(plots.equity_vs_buyhold(tk, edates, strat_eq, bh_eq, p("equity"),
                                                     strategy))

        if "iv" in kinds:
            dts, ivs = implied_vol_timeseries(opt, under)
            if dts:
                rv = realized_vol(under)["realized_vol"]
                paths.append(plots.iv_vs_realized(tk, dts, ivs, rv, p("iv")))

        if "volume" in kinds:
            pcr = daily_put_call_ratio(opt)
            if not pcr.empty:
                d = pcr.reset_index()
                paths.append(plots.volume_and_pcr(
                    tk, list(d["date"]),
                    list(d["put_volume"] + d["call_volume"]),
                    list(d["put_call_ratio"].fillna(0)), p("volume")))

        return {"ticker": tk, "charts": paths, "count": len(paths)}

    return ToolSpec(
        name="make_charts",
        description="Generate analysis charts (PNG) for a ticker: price trend, strategy equity "
                    "vs buy&hold, implied-vs-realized vol, and option volume + put/call ratio. "
                    "The GUI displays them. Returns the saved file paths.",
        parameters=PARAMETERS,
        handler=handler,
        tags=["charts"],
    )
