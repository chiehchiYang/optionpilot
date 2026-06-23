"""Tool: market_sentiment — read the current equity-fear regime (VIX).

Shared by both desks. For the options desk it's the classic fear gauge; for the perp desk it's
the RIGHT sentiment for US-stock perps (NOKUSDT/AAPLUSDT…) — the equity fear of the underlying,
not crypto sentiment. This is a regime CONTEXT, not a buy/sell signal.
"""

from __future__ import annotations

from datetime import date, timedelta

from optionpilot.config import Config
from optionpilot.sentiment import vix_regime
from optionpilot.tools.base import ToolSpec

PARAMETERS = {
    "type": "object",
    "properties": {
        "start": {"type": "string", "description": "ISO date; omit to default to ~15 months ago."},
        "end": {"type": "string", "description": "ISO date; omit to default to today."},
        "lookback": {"type": "integer", "default": 252,
                     "description": "Sessions for the percentile baseline (252 ≈ 1 year)."},
        "symbol": {"type": "string", "default": "^VIX",
                   "description": "'^VIX' (30-day) or '^VIX3M' (3-month)."},
    },
}


def build(config: Config, approve_spend=None) -> ToolSpec:
    def handler(start=None, end=None, lookback=252, symbol="^VIX"):
        from optionpilot.data.market import load_vix
        end = end or date.today().isoformat()
        start = start or (date.fromisoformat(end) - timedelta(days=460)).isoformat()
        try:
            vix = load_vix(start, end, symbol=symbol)
        except Exception as e:  # noqa: BLE001
            return {"ran": False, "reason": f"VIX 載入失敗:{e}"}
        out = vix_regime(vix, lookback=int(lookback))
        out["symbol"], out["start"], out["end"] = symbol, start, end
        return out

    return ToolSpec(
        name="market_sentiment",
        description="Read the current equity market-sentiment regime from the VIX (level, "
                    "percentile vs the past year, regime label). Use for market sentiment / "
                    "市場情緒 / VIX / 恐慌 / 大盤氣氛. For US-stock perps this is the relevant fear "
                    "gauge (the underlying's equity fear), not crypto sentiment. A regime context, "
                    "not a trade signal.",
        parameters=PARAMETERS,
        handler=handler,
        tags=["sentiment"],
    )
