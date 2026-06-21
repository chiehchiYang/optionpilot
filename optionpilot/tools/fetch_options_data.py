"""Tool: fetch_options_data — check availability/cost, then cache a chain.

Estimating cost is free and never prompts. A real (paid) download asks for approval at the
moment of spend (cache hits are free and silent).
"""

from __future__ import annotations

from optionpilot.config import Config
from optionpilot.data.databento_fetcher import CostGuardError, DatabentoFetcher, FetchDenied
from optionpilot.tools.base import ToolSpec

PARAMETERS = {
    "type": "object",
    "properties": {
        "ticker": {"type": "string", "description": "Underlying ticker, e.g. ZETA"},
        "start": {"type": "string", "description": "ISO date"},
        "end": {"type": "string", "description": "ISO date"},
        "estimate_only": {"type": "boolean", "default": False,
                          "description": "If true, only return the estimated cost (free, no download)."},
    },
    "required": ["ticker", "start", "end"],
}


def build(config: Config, approve_spend=None) -> ToolSpec:
    fetcher = DatabentoFetcher(config)

    def handler(ticker, start, end, estimate_only=False):
        parent = ticker if ticker.endswith(".OPT") else f"{ticker.upper()}.OPT"
        est = fetcher.estimate_cost(symbols=[parent], schema="ohlcv-1d",
                                    start=start, end=end, stype_in="parent")
        info = {"ticker": ticker.upper(), "estimated_usd": round(est.usd, 4),
                "records": est.record_count, "guard_usd": config.max_fetch_usd}
        if estimate_only:
            return info
        try:
            df = fetcher.fetch(symbols=[parent], schema="ohlcv-1d", start=start, end=end,
                               stype_in="parent", approve=approve_spend)
        except CostGuardError as e:
            return {**info, "downloaded": False, "blocked_by_guard": str(e)}
        except FetchDenied as e:
            return {**info, "downloaded": False, "denied": str(e)}
        return {**info, "downloaded": True, "rows": len(df)}

    return ToolSpec(
        name="fetch_options_data",
        description="Check Databento OPRA data availability and cost for a ticker, and cache it. "
                    "Estimating is free; a real download asks for approval at the point of spend.",
        parameters=PARAMETERS,
        handler=handler,
        tags=["data"],
    )
