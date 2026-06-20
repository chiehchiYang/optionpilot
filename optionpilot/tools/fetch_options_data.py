"""Tool: fetch_options_data — historical OPRA pull via DatabentoFetcher (approval-gated)."""

from __future__ import annotations

from optionpilot.config import Config
from optionpilot.data.databento_fetcher import DatabentoFetcher
from optionpilot.tools.base import ToolSpec

PARAMETERS = {
    "type": "object",
    "properties": {
        "symbols": {"type": "array", "items": {"type": "string"},
                    "description": "Underlying or OSI option symbols, e.g. ['SPY']"},
        "schema": {"type": "string", "default": "ohlcv-1m",
                   "description": "Databento schema, e.g. ohlcv-1m, trades, cbbo-1m"},
        "start": {"type": "string", "description": "ISO date, e.g. 2024-01-01"},
        "end": {"type": "string", "description": "ISO date, e.g. 2024-03-01"},
    },
    "required": ["symbols", "start", "end"],
}


def build(config: Config) -> ToolSpec:
    fetcher = DatabentoFetcher(config)

    def handler(symbols, start, end, schema="ohlcv-1m"):
        df = fetcher.fetch(symbols=symbols, schema=schema, start=start, end=end)
        return {"rows": len(df), "schema": schema, "symbols": symbols}

    return ToolSpec(
        name="fetch_options_data",
        description="Fetch historical options/underlying data from Databento OPRA. "
                    "Estimates cost first and is approval-gated to protect the credit budget.",
        parameters=PARAMETERS,
        handler=handler,
        requires_approval=True,
        tags=["data"],
    )
