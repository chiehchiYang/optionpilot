"""Tool: measure_vrp — is a ticker's implied vol overpriced vs realized (worth selling)?

Reports implied vol (self-computed), upside/downside realized vol, the variance risk premium,
and buy&hold over the window — so you can judge whether premium-selling has an edge AND
whether you'd be better off just owning the stock.
"""

from __future__ import annotations

from optionpilot.analysis import measure_vrp
from optionpilot.config import Config
from optionpilot.data.market import load_option_chain, load_underlying
from optionpilot.tools.base import ToolSpec

PARAMETERS = {
    "type": "object",
    "properties": {
        "ticker": {"type": "string"},
        "start": {"type": "string"},
        "end": {"type": "string"},
    },
    "required": ["ticker", "start", "end"],
}


def build(config: Config, approve_spend=None) -> ToolSpec:
    def handler(ticker, start, end):
        from optionpilot.data.databento_fetcher import CostGuardError, FetchDenied
        try:
            opt = load_option_chain(config, ticker, start, end, approve=approve_spend)
        except (FetchDenied, CostGuardError) as e:
            return {"ticker": ticker.upper(), "ran": False, "reason": str(e)}
        under = load_underlying(ticker, start, end)
        res = measure_vrp(opt, under)
        res["ticker"] = ticker.upper()
        return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in res.items()}

    return ToolSpec(
        name="measure_vrp",
        description="Measure a ticker's variance risk premium: implied vol (computed) vs "
                    "upside/downside realized vol, plus buy&hold. Use it to judge whether "
                    "selling premium has an edge (IV > downside vol) and whether owning the "
                    "stock would have been better — faster than a full backtest.",
        parameters=PARAMETERS,
        handler=handler,
        tags=["analysis"],
    )
