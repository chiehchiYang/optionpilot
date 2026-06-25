"""Tool: stock_scanner — rank a basket of US stocks by a transparent multi-dimensional scorecard.

Trending/hot scan + sentiment quantification + multi-factor scoring in one pass. Each name is
scored CROSS-SECTIONALLY (percentile vs the others) across four equal-weighted dimensions —
technical, sentiment, fundamental, valuation — plus a 'hotness' (trending) rank. This is a SCREEN
to generate candidates, not a signal: whatever it surfaces must be backtested before you act.
"""

from __future__ import annotations

from optionpilot.config import Config
from optionpilot.tools.base import ToolSpec

# a sector-spread liquid large-cap default basket (used when no tickers are given)
DEFAULT_BASKET = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD", "NFLX",
                  "JPM", "XOM", "WMT", "UNH", "JNJ", "V"]
_RAW_SHOWN = ["ret_1m", "ret_3m", "rsi14", "rel_volume", "trailing_pe", "forward_pe", "peg"]

PARAMETERS = {
    "type": "object",
    "properties": {
        "tickers": {"type": "array", "items": {"type": "string"},
                    "description": "US tickers to rank (2-25). Omit to use a default large-cap "
                                   "basket. Cross-sectional scoring needs >=2 names."},
        "rank_by": {"type": "string", "default": "hotness",
                    "enum": ["hotness", "composite", "technical", "sentiment", "fundamental",
                             "valuation"],
                    "description": "Sort key. 'hotness'=trending/active now; 'composite'=all four "
                                   "dimensions; or a single dimension."},
        "lookback_days": {"type": "integer", "default": 400,
                          "description": "Calendar days of price history (>=300 for 200-day MA)."},
        "include_fundamentals": {"type": "boolean", "default": True,
                                 "description": "Pull valuation/fundamentals (slower, 1 call/name); "
                                                "False = technical+sentiment only."},
        "top": {"type": "integer", "default": 10, "description": "How many to return."},
    },
}


def build(config: Config, approve_spend=None) -> ToolSpec:
    def handler(tickers=None, rank_by="hotness", lookback_days=400,
                include_fundamentals=True, top=10):
        from datetime import date, timedelta

        from optionpilot.data.market import load_fundamentals, load_ohlcv
        from optionpilot.screener import metrics_for, score_universe

        syms = [t.upper() for t in (tickers or DEFAULT_BASKET)][:25]
        if len(syms) < 2:
            return {"ran": False, "reason": "至少要 2 檔才能做橫斷面評分"}
        end = date.today().isoformat()
        start = (date.today() - timedelta(days=int(lookback_days))).isoformat()

        rows, skipped = {}, []
        for sym in syms:
            try:
                ohlcv = load_ohlcv(sym, start, end)
            except Exception as e:  # noqa: BLE001
                skipped.append(f"{sym}: {type(e).__name__}")
                continue
            fund = None
            if include_fundamentals:
                try:
                    fund = load_fundamentals(sym)
                except Exception:  # noqa: BLE001 - fundamentals are best-effort
                    fund = None
            m = metrics_for(ohlcv, fund)
            if m:
                rows[sym] = m
        if len(rows) < 2:
            return {"ran": False, "reason": "可用資料的標的不足 2 檔", "skipped": skipped}

        scored = score_universe(rows)

        def key(item):
            t, sc = item
            v = sc["dimensions"].get(rank_by) if rank_by in ("technical", "sentiment",
                                                             "fundamental", "valuation") \
                else sc.get(rank_by)
            return v if v is not None else -1.0

        ranked = sorted(scored.items(), key=key, reverse=True)[:int(top)]
        out_rows = [{
            "ticker": t,
            "composite": sc["composite"], "hotness": sc["hotness"],
            "dimensions": sc["dimensions"],
            "key_metrics": {k: sc["raw"].get(k) for k in _RAW_SHOWN if k in sc["raw"]},
        } for t, sc in ranked]

        return {
            "ran": True, "rank_by": rank_by, "universe_size": len(rows),
            "skipped": skipped, "ranked": out_rows,
            "note": ("橫斷面百分位、四維等權,純屬 SCREEN(產生假設用),非買賣訊號;情緒是價格動能"
                     "代理(無新聞NLP/暗池流)。鎖定的標的請用 run_backtest/regime_backtest 驗證。"),
        }

    return ToolSpec(
        name="stock_scanner",
        description="Scan/rank a basket of US stocks (熱門股掃描 / 選股 / 多維分析). Cross-sectional "
                    "percentile scorecard across four equal-weighted dimensions (technical, "
                    "sentiment, fundamental, valuation) plus a 'hotness' trending rank. Use for "
                    "'which names are hot/trending', sentiment quantification, or a multi-factor "
                    "compare. A hypothesis-generating screen, NOT a signal — backtest what it "
                    "surfaces. Free data (yfinance); fundamentals are best-effort.",
        parameters=PARAMETERS,
        handler=handler,
        tags=["screener", "stocks"],
    )
