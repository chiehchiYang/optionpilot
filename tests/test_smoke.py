"""Smoke tests for the pieces that are fully implemented (no API/network needed)."""

import numpy as np

from optionpilot.agent.doom_loop import DoomLoopDetector
from optionpilot.agent.router import ToolRouter
from optionpilot.backtest import max_drawdown, sharpe_ratio, summarize, win_rate
from optionpilot.config import Config
from optionpilot.data.greeks import black_scholes_price, greeks, implied_volatility
from optionpilot.models import NudgeLayer, NudgeRule
from optionpilot.tools import default_tools


def test_config_loads():
    c = Config.load(dotenv=False)
    assert c.model
    assert c.max_fetch_usd > 0


def test_black_scholes_put_call_parity():
    S, K, T, r, sigma = 100.0, 100.0, 1.0, 0.05, 0.2
    call = black_scholes_price(S, K, T, r, sigma, "call")
    put = black_scholes_price(S, K, T, r, sigma, "put")
    # C - P = S - K e^{-rT}
    assert abs((call - put) - (S - K * np.exp(-r * T))) < 1e-6


def test_implied_vol_roundtrip():
    S, K, T, r, true_sigma = 100.0, 105.0, 0.5, 0.03, 0.25
    price = black_scholes_price(S, K, T, r, true_sigma, "call")
    iv = implied_volatility(price, S, K, T, r, "call")
    assert abs(iv - true_sigma) < 1e-3


def test_greeks_call_delta_range():
    g = greeks(100, 100, 1.0, 0.05, 0.2, "call")
    assert 0.0 < g.delta < 1.0
    assert g.gamma > 0
    assert g.vega > 0


def test_metrics_basic():
    rng = np.random.default_rng(0)
    r = rng.normal(0.001, 0.01, size=300)
    s = summarize(r, turnover=0.5)
    assert "sharpe" in s and "max_drawdown" in s and "win_rate" in s
    assert s["max_drawdown"] <= 0
    assert 0 <= s["win_rate"] <= 1
    assert sharpe_ratio(r) == s["sharpe"]
    assert max_drawdown(r) == s["max_drawdown"]
    assert win_rate(r) == s["win_rate"]


def test_nudge_layer_clips_and_ablates():
    rule = NudgeRule("oversold", lambda f: 1.0 if f["rsi"] < 30 else 0.0, weight=0.2)
    layer = NudgeLayer(rules=[rule])
    p = np.array([0.5, 0.95])
    feats = [{"rsi": 25}, {"rsi": 25}]
    out = layer.apply(p, feats)
    assert out[0] == 0.7  # 0.5 + 0.2
    assert out[1] == 1.0  # clipped
    # disabled => passthrough (ablation baseline)
    layer.enabled = False
    assert list(layer.apply(p, feats)) == [0.5, 0.95]


def test_router_dispatch_errors_are_strings():
    r = ToolRouter()
    assert r.dispatch("nope", {}).startswith("ERROR: unknown tool")


def test_doom_loop_detects_repetition():
    d = DoomLoopDetector(window=6, threshold=3)
    assert d.record("t", {"a": 1}) is None
    assert d.record("t", {"a": 1}) is None
    msg = d.record("t", {"a": 1})
    assert msg and "repeating" in msg


def test_default_tools_build():
    specs = default_tools(Config.load(dotenv=False))
    names = {s.name for s in specs}
    assert names == {
        "fetch_options_data", "calculate_features", "predict_buy_point",
        "run_backtest", "generate_report",
    }
    # the data fetch must be approval-gated
    assert next(s for s in specs if s.name == "fetch_options_data").requires_approval
