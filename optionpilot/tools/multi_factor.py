"""Tool: multi_factor_analysis — one stock's multi-dimensional scorecard vs a peer basket.

Scores ONE ticker across technical + sentiment + fundamental + valuation, relative to a peer set
(cross-sectional percentile — a name is "cheap"/"strong" only vs its peers). Shows each dimension,
where it ranks in the basket, and the raw metrics behind it. A research scorecard, not a signal.
"""

from __future__ import annotations

from optionpilot.config import Config
from optionpilot.tools.base import ToolSpec
from optionpilot.tools.stock_scanner import DEFAULT_BASKET

PARAMETERS = {
    "type": "object",
    "properties": {
        "ticker": {"type": "string", "description": "The US stock to analyze."},
        "peers": {"type": "array", "items": {"type": "string"},
                  "description": "Peer tickers for the cross-sectional context (relative scoring). "
                                 "Omit to use a default large-cap basket."},
        "lookback_days": {"type": "integer", "default": 400},
        "include_fundamentals": {"type": "boolean", "default": True},
    },
    "required": ["ticker"],
}


def build(config: Config, approve_spend=None) -> ToolSpec:
    def handler(ticker, peers=None, lookback_days=400, include_fundamentals=True):
        from datetime import date, timedelta

        from optionpilot.data.market import load_fundamentals, load_ohlcv
        from optionpilot.screener import metrics_for, score_universe

        tk = ticker.upper()
        basket = [tk] + [p.upper() for p in (peers or DEFAULT_BASKET) if p.upper() != tk]
        basket = list(dict.fromkeys(basket))[:25]
        end = date.today().isoformat()
        start = (date.today() - timedelta(days=int(lookback_days))).isoformat()

        rows, skipped = {}, []
        for sym in basket:
            try:
                ohlcv = load_ohlcv(sym, start, end)
            except Exception as e:  # noqa: BLE001
                skipped.append(f"{sym}: {type(e).__name__}")
                continue
            fund = None
            if include_fundamentals:
                try:
                    fund = load_fundamentals(sym)
                except Exception:  # noqa: BLE001
                    fund = None
            m = metrics_for(ohlcv, fund)
            if m:
                rows[sym] = m
        if tk not in rows:
            return {"ran": False, "ticker": tk, "reason": "目標股無可用資料", "skipped": skipped}

        scored = score_universe(rows)
        me = scored[tk]
        # where the ticker ranks within the basket per dimension + composite (1 = best)
        ranks = {}
        for dim in ("composite", "technical", "sentiment", "fundamental", "valuation"):
            def val(sc, d=dim):
                return sc["composite"] if d == "composite" else sc["dimensions"].get(d)
            vals = [val(sc) for sc in scored.values() if val(sc) is not None]
            mine = val(me)
            if mine is not None and vals:
                ranks[dim] = {"rank": 1 + sum(1 for v in vals if v > mine), "of": len(vals)}

        return {
            "ran": True, "ticker": tk, "peers_used": len(rows) - 1,
            "composite": me["composite"], "dimensions": me["dimensions"],
            "hotness": me["hotness"], "rank_in_basket": ranks, "raw": me["raw"],
            "skipped": skipped,
            "note": ("分數=相對這組 peer 的橫斷面百分位(四維等權),情緒為價格動能代理。這是研究"
                     "用 scorecard,不是買賣訊號;有興趣的角度請用回測工具驗證。"),
        }

    return ToolSpec(
        name="multi_factor_analysis",
        description="Multi-dimensional scorecard for ONE US stock vs a peer basket (多維分析: "
                    "技術+情緒+基本面+估值). Cross-sectional percentile per dimension, the name's "
                    "rank in the basket, and the raw metrics. A research scorecard, not a signal — "
                    "validate any thesis with the backtest tools. Free data (yfinance).",
        parameters=PARAMETERS,
        handler=handler,
        tags=["screener", "stocks"],
    )
