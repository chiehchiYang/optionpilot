"""Tool: support_resistance — algorithmic support/resistance levels for a ticker.

Computes swing lows/highs (local extrema) and classic floor-trader pivot points from the
underlying's recent OHLC (yfinance). Deterministic levels, not a discretionary forecast.
"""

from __future__ import annotations

import pandas as pd

from optionpilot.analysis import support_resistance
from optionpilot.config import Config
from optionpilot.tools.base import ToolSpec

PARAMETERS = {
    "type": "object",
    "properties": {
        "ticker": {"type": "string"},
        "lookback_days": {"type": "integer", "default": 120,
                          "description": "Calendar lookback for swing levels."},
    },
    "required": ["ticker"],
}


def build(config: Config, approve_spend=None, interactive: bool = True) -> ToolSpec:
    def handler(ticker, lookback_days=120):
        import yfinance as yf

        df = yf.download(ticker.upper(), period=f"{max(lookback_days * 2, 90)}d",
                         progress=False, auto_adjust=False)
        if df.empty:
            return {"ticker": ticker.upper(), "ran": False, "reason": "no price data"}
        if isinstance(df.columns, pd.MultiIndex):  # yfinance single-ticker MultiIndex
            df.columns = df.columns.get_level_values(0)
        res = support_resistance(df, lookback=lookback_days)
        res["ticker"] = ticker.upper()
        return res

    return ToolSpec(
        name="support_resistance",
        description="Compute algorithmic support/resistance levels for a ticker: recent swing "
                    "lows (support) and highs (resistance) plus classic pivot points (P, S1-S3, "
                    "R1-R3). Deterministic price levels, not a forecast.",
        parameters=PARAMETERS,
        handler=handler,
        tags=["analysis"],
    )
