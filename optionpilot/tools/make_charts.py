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
        skipped: dict[str, str] = {}

        def p(kind):
            return out_dir / f"{tk}_{kind}_{stamp}.png"

        def _asof(d):
            s = under[under.index <= d]
            return float(s.iloc[-1]) if len(s) else float(under.iloc[0])

        for kind in kinds:
            try:
                if kind == "price":
                    paths.append(plots.price_trend(tk, list(under.index), list(under.values),
                                                   p("price")))
                elif kind == "equity":
                    res = _BT.get(strategy, cash_secured_put_backtest)(
                        opt, under, CSPParams(min_contract_volume=10))
                    if not res.trades:
                        skipped["equity"] = f"{strategy} 在此期間沒有產生任何交易,無法畫權益曲線"
                        continue
                    edates = [t["entry"] for t in res.trades]
                    strat_eq = list(np.cumprod([1 + t["return"] for t in res.trades]))
                    base = _asof(edates[0])
                    bh_eq = [_asof(d) / base for d in edates]
                    paths.append(plots.equity_vs_buyhold(tk, edates, strat_eq, bh_eq, p("equity"),
                                                         strategy))
                elif kind == "iv":
                    dts, ivs = implied_vol_timeseries(opt, under)
                    if not dts:
                        skipped["iv"] = "沒有足夠的 ATM 期權報價可估算隱含波動率"
                        continue
                    rv = realized_vol(under)["realized_vol"]
                    paths.append(plots.iv_vs_realized(tk, dts, ivs, rv, p("iv")))
                elif kind == "volume":
                    pcr = daily_put_call_ratio(opt)
                    if pcr.empty:
                        skipped["volume"] = "沒有成交量資料"
                        continue
                    d = pcr.reset_index()
                    paths.append(plots.volume_and_pcr(
                        tk, list(d["date"]),
                        list(d["put_volume"] + d["call_volume"]),
                        list(d["put_call_ratio"].fillna(0)), p("volume")))
            except Exception as e:  # noqa: BLE001 - one bad chart must not kill the others
                skipped[kind] = f"生成失敗:{type(e).__name__}"

        return {"ticker": tk, "made": [kind for kind in kinds if kind not in skipped],
                "charts": paths, "skipped": skipped, "count": len(paths)}

    return ToolSpec(
        name="make_charts",
        description="Generate analysis charts (PNG) for a ticker: price trend, strategy equity "
                    "vs buy&hold, implied-vs-realized vol, and option volume + put/call ratio. "
                    "The GUI displays them. Returns the saved file paths.",
        parameters=PARAMETERS,
        handler=handler,
        tags=["charts"],
    )
