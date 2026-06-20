# OptionPilot

An autonomous **options-strategy research agent** — think of it as an *ML intern for options*.
Given a natural-language task, it runs the full research loop itself: fetch data → engineer
features → predict buy points (with a **Nudge** layer) → backtest → ablation → report, and
proves every signal with rigorous backtesting instead of asking you to trust a black box.

> Architecture borrows patterns from [huggingface/ml-intern](https://github.com/huggingface/ml-intern)
> (agentic loop, ContextManager, ToolRouter, approval gating, doom-loop detection) but is written
> fresh with no Hugging Face coupling, specialized for options-strategy research.

## Status

Early scaffold. See [plan.md](plan.md) for the full design and roadmap.

## Key design decisions

| Area | Choice |
|---|---|
| Backtest data | Databento OPRA (historical, pay-as-you-go; $125 free credit), greeks computed locally |
| Live quotes | deferred (yfinance delayed quotes when needed; no paid live feed) |
| Nudge | post-processing rule-reweight layer → supports ablation |
| Agent harness | written fresh, borrowing ml-intern patterns; multi-model via LiteLLM |
| Signals | options-flow signals (put/call ratio, unusual activity) as features, validated by backtest |
| Cost control | fetch-size/cost guard + approval gating on expensive pulls |

## Quick start

```bash
uv sync                       # install
cp .env.example .env          # add DATABENTO_API_KEY + an LLM key
optionpilot "分析 SPY 的買點策略"   # headless
optionpilot                   # interactive
```

### Local model (zero-cost dev)

Run a local OpenAI-compatible server and point OptionPilot at it — no API key, no rate limits.

```bash
bash scripts/serve_local.sh   # vLLM serving Qwen3-Coder-30B-A3B (FP8) on one GPU
```

Then in `.env`:

```
OPTIONPILOT_MODEL=hosted_vllm/Qwen/Qwen3-Coder-30B-A3B-Instruct-FP8
OPTIONPILOT_API_BASE=http://localhost:8000/v1
OPTIONPILOT_API_KEY=local
```

Caches are kept on `/media/user/data2` (the root disk is small); see the script header.

## Layout

```
optionpilot/
  cli.py            Typer entry (interactive / headless)
  config.py         config hierarchy (env > defaults)
  llm/              LiteLLM client wrapper
  agent/            experiment loop, context manager, tool router, doom-loop, approval, planner
  tools/            fetch_options_data, calculate_features, predict_buy_point, run_backtest, generate_report
  data/             Databento fetcher (+ cost guard), Black-Scholes greeks
  models/           XGBoost baseline, NudgeLayer
  backtest/         engine + metrics (Sharpe / MaxDD / WinRate / turnover)
  tracking/         experiment tracker (DuckDB)
```
