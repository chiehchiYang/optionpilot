"""Tool: regime_backtest — does a VIX-sentiment entry filter actually improve put-selling?

Runs the cash-secured-put backtest twice over the same window — once unfiltered (baseline), once
entering ONLY when the VIX percentile is in a chosen band (e.g. sell puts only when fear is above
its running median, so premium is richer) — and compares both to buy&hold. The filter uses a
lookahead-free expanding percentile, so this is an honest test of whether the regime edge is real.
"""

from __future__ import annotations

from optionpilot.backtest.strategies import CSPParams, cash_secured_put_backtest
from optionpilot.config import Config
from optionpilot.sentiment import vix_regime
from optionpilot.tools.base import ToolSpec

PARAMETERS = {
    "type": "object",
    "properties": {
        "ticker": {"type": "string"},
        "start": {"type": "string"},
        "end": {"type": "string"},
        "vix_pct_min": {"type": "number", "default": 50.0,
                        "description": "Only enter when VIX expanding-percentile >= this "
                                       "(sell into elevated fear). 50 = above running median."},
        "vix_pct_max": {"type": "number",
                        "description": "Optional upper bound on the VIX percentile band."},
        "min_contract_volume": {"type": "integer", "default": 10},
    },
    "required": ["ticker", "start", "end"],
}

_KEYS = ["n_trades", "total_return", "benchmark_buy_hold", "excess_vs_buy_hold",
         "sharpe_annualized", "max_drawdown", "win_rate", "assigned_rate"]


def build(config: Config, approve_spend=None) -> ToolSpec:
    def handler(ticker, start, end, vix_pct_min=50.0, vix_pct_max=None, min_contract_volume=10):
        from optionpilot.data.databento_fetcher import CostGuardError, FetchDenied
        from optionpilot.data.market import load_option_chain, load_underlying, load_vix
        tk = ticker.upper()
        try:
            opt = load_option_chain(config, tk, start, end, approve=approve_spend)
        except (FetchDenied, CostGuardError) as e:
            return {"ticker": tk, "ran": False, "reason": str(e)}
        under = load_underlying(tk, start, end)
        try:
            vix = load_vix(start, end)
        except Exception as e:  # noqa: BLE001 - VIX is the whole point; report if unavailable
            return {"ticker": tk, "ran": False, "reason": f"VIX 載入失敗:{e}"}

        base_p = CSPParams(min_contract_volume=int(min_contract_volume))
        filt_p = CSPParams(min_contract_volume=int(min_contract_volume),
                           vix_pct_min=vix_pct_min, vix_pct_max=vix_pct_max)
        baseline = cash_secured_put_backtest(opt, under, base_p).metrics
        filtered = cash_secured_put_backtest(opt, under, filt_p, vix=vix).metrics

        def pick(m):
            return {k: (round(m[k], 4) if isinstance(m.get(k), float) else m.get(k))
                    for k in _KEYS if k in m}

        b_ex = baseline.get("excess_vs_buy_hold")
        f_ex = filtered.get("excess_vs_buy_hold")
        improved = (b_ex is not None and f_ex is not None and f_ex > b_ex)
        thin = (filtered.get("n_trades", 0) or 0) < 10
        return {
            "ticker": tk, "ran": True, "start": start, "end": end,
            "vix_now": vix_regime(vix),
            "filter": {"vix_pct_min": vix_pct_min, "vix_pct_max": vix_pct_max},
            "baseline": pick(baseline),
            "regime_filtered": pick(filtered),
            "filter_improved_excess": improved,
            "note": (
                ("濾網提升了相對 buy&hold 的超額報酬" if improved else
                 "濾網並未提升超額報酬(甚至更差)——這個 regime edge 在此標的/期間不成立")
                + ("。注意:濾後交易數 <10,樣本太小,結論僅供參考。" if thin else "。")
                + " baseline=不過濾;regime_filtered=只在 VIX 百分位達標時進場。永遠對比 buy&hold。"
            ),
        }

    return ToolSpec(
        name="regime_backtest",
        description="Test whether a VIX market-sentiment entry filter improves cash-secured-put "
                    "selling: backtests unfiltered vs. entering only in the chosen VIX percentile "
                    "regime, both vs buy&hold. Lookahead-free. Use when the user asks about market "
                    "sentiment / 市場情緒 / VIX / 恐慌 regime conditioning of an options strategy.",
        parameters=PARAMETERS,
        handler=handler,
        tags=["backtest", "sentiment"],
    )
