"""Tool: grid_backtest — backtest a long-only grid bot on a Binance USDⓈ-M perpetual.

For crypto OR US-stock perps (NOKUSDT/AAPLUSDT/SPYUSDT…). Pulls public klines (no API key),
runs the grid, and returns the honest split: booked grid profit vs. marked-to-market loss on
stuck inventory, time spent outside the grid, and the buy&hold benchmark.
"""

from __future__ import annotations

from optionpilot.backtest.grid import GridParams, grid_backtest
from optionpilot.config import Config
from optionpilot.tools.base import ToolSpec

PARAMETERS = {
    "type": "object",
    "properties": {
        "symbol": {"type": "string",
                   "description": "Binance USDⓈ-M perp, e.g. BTCUSDT, NOKUSDT, AAPLUSDT."},
        "interval": {"type": "string", "default": "1h",
                     "description": "Kline interval; use a FINE one for grids: 15m/1h. e.g. "
                                    "5m,15m,1h,4h,1d."},
        "bars": {"type": "integer", "default": 1000,
                 "description": "How many recent klines to test (<=1500)."},
        "n_grids": {"type": "integer", "default": 20},
        "capital": {"type": "number", "default": 10000.0,
                    "description": "USDT budget; sizes per-grid quantity."},
        "lower": {"type": "number", "description": "Grid bottom. Omit to auto-set (uses lookahead "
                                                   "— optimistic; the result flags it)."},
        "upper": {"type": "number", "description": "Grid top. Omit to auto-set (see lower)."},
        "spacing": {"type": "string", "enum": ["arith", "geom"], "default": "arith"},
        "include_funding": {"type": "boolean", "default": True,
                            "description": "Apply the mean funding rate as a long-carry drag."},
        "vix_pct_max": {"type": "number", "default": 60.0,
                        "description": "VIX regime gate: also run a variant that only ADDS "
                                       "inventory when VIX percentile <= this (grids prefer calm; "
                                       "the right fear gauge for US-stock perps). null to skip."},
        "composite_pct_max": {"type": "number", "default": 60.0,
                              "description": "Composite regime gate: also run a variant that only "
                                             "ADDS inventory when the blended perp-risk percentile "
                                             "(vol + funding + long/short + VIX) <= this. null to "
                                             "skip."},
    },
    "required": ["symbol"],
}

_KEYS = ["total_return", "buy_hold_return", "excess_vs_buy_hold", "max_drawdown", "n_roundtrips",
         "open_unrealized_pnl", "funding_paid", "pct_time_below_lower",
         "buys_skipped_by_vix", "buys_skipped_by_composite"]
_LS_PERIODS = {"5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"}


def build(config: Config, approve_spend=None) -> ToolSpec:
    def handler(symbol, interval="1h", bars=1000, n_grids=20, capital=10000.0,
                lower=None, upper=None, spacing="arith", include_funding=True,
                vix_pct_max=60.0, composite_pct_max=60.0):
        from datetime import timedelta

        from optionpilot.crypto import funding_summary
        from optionpilot.data import binance
        sym = symbol.upper()
        try:
            kl = binance.klines(sym, interval=interval, limit=bars)
        except Exception as e:  # noqa: BLE001
            return {"symbol": sym, "ran": False, "reason": f"{type(e).__name__}: {e}"}
        if kl.empty:
            return {"symbol": sym, "ran": False, "reason": "查無 K 線(symbol 可能不存在)"}

        # raw funding history powers BOTH the carry drag and the composite regime
        try:
            fdf = binance.funding_rate_history(sym, limit=500)
        except Exception:  # noqa: BLE001
            fdf = None
        funding_8h = None
        if include_funding and fdf is not None and not fdf.empty:
            funding_8h = funding_summary(fdf).get("mean_rate")

        # VIX shared by both gated variants; loaded once (None if it fails -> variants degrade)
        vix = None
        if vix_pct_max is not None or composite_pct_max is not None:
            try:
                from optionpilot.data.market import load_vix
                vstart = (kl.index[0].date() - timedelta(days=365)).isoformat()
                vend = (kl.index[-1].date() + timedelta(days=1)).isoformat()
                vix = load_vix(vstart, vend)
            except Exception:  # noqa: BLE001 - VIX is a bonus input, never block the grid
                vix = None

        def gp(**extra):
            return GridParams(lower=lower, upper=upper, n_grids=int(n_grids),
                              capital=float(capital), spacing=spacing,
                              funding_per_8h=funding_8h, **extra)

        def strip(r):
            return {k: v for k, v in r.items() if not k.startswith("_")}

        def improved(variant):
            be, ve = res["baseline"].get("excess_vs_buy_hold"), variant.get("excess_vs_buy_hold")
            return be is not None and ve is not None and ve > be

        res = strip(grid_backtest(kl, gp()))
        res["symbol"], res["interval"] = sym, interval
        res["funding_per_8h_used"] = funding_8h
        res["baseline"] = {k: res.get(k) for k in _KEYS}

        # VIX-only regime variant (the equity fear gauge — right for US-stock perps)
        if vix_pct_max is not None and vix is not None:
            from optionpilot.sentiment import vix_regime
            gated = strip(grid_backtest(kl, gp(vix_pct_max=vix_pct_max), vix=vix))
            res["vix_now"] = vix_regime(vix)
            res["vix_variant"] = {k: gated.get(k) for k in _KEYS}
            res["vix_gate_improved"] = improved(gated)
        elif vix_pct_max is not None:
            res["vix_note"] = "VIX regime 變體略過(VIX 載入失敗)"

        # COMPOSITE regime variant (PSCI: vol + funding + long/short + VIX blended)
        if composite_pct_max is not None:
            try:
                from optionpilot.sentiment import perp_regime, perp_risk_series
                ls_period = interval if interval in _LS_PERIODS else "1h"
                try:
                    lsdf = binance.long_short_ratio(sym, period=ls_period, limit=500)
                except Exception:  # noqa: BLE001 - long/short is ~30d only; optional
                    lsdf = None
                regime = perp_risk_series(kl, funding=fdf, long_short=lsdf, vix=vix)
                comp = strip(grid_backtest(kl, gp(regime_pct_max=composite_pct_max), regime=regime))
                res["composite_now"] = perp_regime(kl, funding=fdf, long_short=lsdf, vix=vix)
                res["composite_variant"] = {k: comp.get(k) for k in _KEYS}
                res["composite_gate_improved"] = improved(comp)
            except Exception as e:  # noqa: BLE001 - composite overlay is a bonus, never block
                res["composite_note"] = f"複合 regime 變體略過:{e}"

        if res.get("auto_range_in_sample"):
            res["warning"] = ("區間是用整段資料的百分位自動推得(含未來資訊,偏樂觀);實盤必須"
                              "事先設定上下界。請看 pct_time_below_lower 評估跌穿風險。")
        return res

    return ToolSpec(
        name="grid_backtest",
        description="Backtest a long-only GRID bot on a Binance USDⓈ-M perpetual (crypto or "
                    "US-stock perp). Returns booked grid profit vs. stuck-inventory unrealized "
                    "loss, time outside the grid, fees + funding drag, and the buy&hold "
                    "benchmark. Also runs two regime variants that only add inventory in calm "
                    "regimes and reports whether each gate helped: a VIX-only gate (equity fear "
                    "gauge, right for US-stock perps) and a COMPOSITE gate (PSCI: vol + funding + "
                    "long/short + VIX blended). Public data, no API key, no order "
                    "placement. Use a fine interval "
                    "(15m/1h). For range-bound names a grid shines; in a downtrend it bleeds — "
                    "the result shows which.",
        parameters=PARAMETERS,
        handler=handler,
        tags=["crypto", "backtest"],
    )
