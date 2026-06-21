"""Tool: detect_unusual_activity — Stockwe-style options-flow screening for a ticker.

Loads the option chain and returns the top volume-spike contracts plus the latest put/call
ratio. A screening aid surfaced for the analyst, not a standalone trade signal.
"""

from __future__ import annotations

from optionpilot.config import Config
from optionpilot.data.market import load_option_chain
from optionpilot.signals import daily_put_call_ratio, unusual_volume
from optionpilot.tools.base import ToolSpec

PARAMETERS = {
    "type": "object",
    "properties": {
        "ticker": {"type": "string"},
        "start": {"type": "string"},
        "end": {"type": "string"},
        "ratio_threshold": {"type": "number", "default": 5.0,
                            "description": "Flag volume >= this multiple of trailing average."},
        "min_volume": {"type": "integer", "default": 200},
        "top_n": {"type": "integer", "default": 10},
    },
    "required": ["ticker", "start", "end"],
}


def build(config: Config) -> ToolSpec:
    def handler(ticker, start, end, ratio_threshold=5.0, min_volume=200, top_n=10):
        opt = load_option_chain(config, ticker, start, end)
        ua = unusual_volume(opt, ratio_threshold=ratio_threshold, min_volume=min_volume)
        pcr = daily_put_call_ratio(opt)
        top = [
            {"date": str(r["date"]), "contract": str(r["contract"]).strip(),
             "volume": int(r["volume"]), "avg_volume": round(float(r["avg_volume"]), 1),
             "ratio": round(float(r["ratio"]), 1)}
            for _, r in ua.head(top_n).iterrows()
        ]
        latest_pcr = None
        if not pcr.empty:
            last = pcr.dropna().tail(1)
            if not last.empty:
                latest_pcr = round(float(last["put_call_ratio"].iloc[0]), 3)
        return {"ticker": ticker.upper(), "unusual_contracts": top,
                "latest_put_call_ratio": latest_pcr, "flagged_count": len(ua)}

    return ToolSpec(
        name="detect_unusual_activity",
        description="Screen a ticker's option chain for unusual activity: contracts whose "
                    "volume spikes far above their trailing average, plus the latest put/call "
                    "volume ratio.",
        parameters=PARAMETERS,
        handler=handler,
        tags=["signal"],
    )
