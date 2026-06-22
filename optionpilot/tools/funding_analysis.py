"""Tool: funding_analysis — the funding-carry edge on a Binance USDⓈ-M perpetual.

Pulls public funding-rate history (no API key) for a perp symbol (crypto OR a US-stock perp
like NOKUSDT/AAPLUSDT/SPYUSDT), and reports the annualized funding, who pays whom, and the
structurally-favoured carry side. This is the crypto/perp analog of measure_vrp.
"""

from __future__ import annotations

from optionpilot.config import Config
from optionpilot.crypto import funding_summary, realized_vol_from_klines
from optionpilot.tools.base import ToolSpec

PARAMETERS = {
    "type": "object",
    "properties": {
        "symbol": {"type": "string",
                   "description": "Binance USDⓈ-M perp symbol, e.g. BTCUSDT, NOKUSDT, AAPLUSDT."},
        "limit": {"type": "integer", "default": 1000,
                  "description": "How many recent funding intervals to fetch (<=1000, 8h each)."},
    },
    "required": ["symbol"],
}


def build(config: Config, approve_spend=None) -> ToolSpec:
    def handler(symbol, limit=1000):
        from optionpilot.data import binance
        sym = symbol.upper()
        try:
            funding = binance.funding_rate_history(sym, limit=limit)
        except Exception as e:  # noqa: BLE001 - network/symbol errors -> report, don't crash
            return {"symbol": sym, "ran": False, "reason": f"{type(e).__name__}: {e}"}
        if funding.empty:
            return {"symbol": sym, "ran": False,
                    "reason": "查無 funding 資料(symbol 可能不存在或非永續合約)"}

        res = funding_summary(funding)
        res["symbol"] = sym
        # context: realized vol of the underlying perp, so the agent can weigh carry vs risk
        try:
            kl = binance.klines(sym, interval="1d", limit=180)
            rv = realized_vol_from_klines(kl)
            res["underlying_realized_vol"] = round(rv.get("realized_vol", 0.0), 4)
            res["underlying_downside_vol"] = round(rv.get("downside_vol", 0.0), 4)
        except Exception:  # noqa: BLE001 - vol is a bonus; funding is the answer
            pass
        return {k: (round(v, 6) if isinstance(v, float) else v) for k, v in res.items()}

    return ToolSpec(
        name="funding_analysis",
        description="Analyze the funding-rate carry on a Binance USDⓈ-M perpetual futures symbol "
                    "(crypto or US-stock perp like NOKUSDT/AAPLUSDT/SPYUSDT). Reports annualized "
                    "funding, who pays (longs vs shorts), the favoured carry side, and the "
                    "underlying's realized vol. The perp analog of measure_vrp — public data, no "
                    "API key.",
        parameters=PARAMETERS,
        handler=handler,
        tags=["crypto", "analysis"],
    )
