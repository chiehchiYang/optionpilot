"""Tool: fundamentals_research — a stock's RECENT fundamentals (quarterly trend + snapshot).

Pulls the last few quarters of income-statement lines (revenue, margins, net income, EPS),
computes YoY/QoQ growth and the margin trend, and adds the current valuation snapshot + next
earnings date. Fundamental CONTEXT, not a trade signal — validate any thesis with the backtest
tools (and mind that IV balloons around earnings).
"""

from __future__ import annotations

from optionpilot.config import Config
from optionpilot.tools.base import ToolSpec

PARAMETERS = {
    "type": "object",
    "properties": {
        "ticker": {"type": "string", "description": "US stock to research, e.g. NVDA."},
        "quarters": {"type": "integer", "default": 8,
                     "description": "How many recent quarters of income statement to pull (<=12)."},
    },
    "required": ["ticker"],
}


def build(config: Config, approve_spend=None) -> ToolSpec:
    def handler(ticker, quarters=8):
        from optionpilot.data.market import load_financials
        from optionpilot.fundamentals import summarize_fundamentals

        tk = ticker.upper()
        try:
            fin = load_financials(tk, quarters=int(quarters))
        except Exception as e:  # noqa: BLE001
            return {"ran": False, "ticker": tk, "reason": f"{type(e).__name__}: {e}"}
        if not fin["quarterly"] and not fin["snapshot"]:
            return {"ran": False, "ticker": tk, "reason": "查無基本面資料(ticker 可能不存在)"}

        out = summarize_fundamentals(fin["quarterly"], fin["snapshot"], fin["next_earnings"])
        out["ran"], out["ticker"] = True, tk
        return out

    return ToolSpec(
        name="fundamentals_research",
        description="Research a US stock's RECENT fundamentals (基本面 / 財報 / 營收 / 獲利 / 估值): "
                    "the last few quarters of revenue, margins, net income and EPS with YoY/QoQ "
                    "growth and margin trend, plus the current valuation snapshot and next "
                    "earnings date. Fundamental CONTEXT, not a signal — backtest any thesis. Free "
                    "data (yfinance, best-effort).",
        parameters=PARAMETERS,
        handler=handler,
        tags=["fundamentals", "stocks"],
    )
