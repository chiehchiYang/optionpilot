# OptionPilot

An autonomous **options-strategy research agent** — think of it as an *ML intern for options*.
Given a natural-language task, it runs the full research loop itself: fetch data → engineer
features → model a signal → backtest → report, and proves every signal with rigorous
out-of-sample backtesting instead of asking you to trust a black box.

## Goal

OptionPilot stands on two pillars:

1. **An ml-intern-style autonomous research loop.** Give it a task ("research credit-spread
   strategies on SPY") and it runs the experiment loop itself — propose a hypothesis → fetch
   data → engineer features → model/strategy → backtest → read metrics → propose the next
   improvement → iterate → deliver the best strategy with a full, honest experiment log. It
   proposes, iterates, and records on its own (`ExperimentLoop` + `Planner` + `ExperimentTracker`).

2. **A rigorous, verifiable backtesting system.** Every strategy must pass the same honest bar:
   out-of-sample / walk-forward evaluation, realistic costs (spread, slippage, fees, assignment),
   full metrics (Sharpe, max drawdown, win rate, turnover) plus worst-case stress tests,
   reproducible head-to-head run comparison, and honest reporting of negative results.

**Success** is not "find a magic money signal" — it's being able to answer, for any candidate
strategy, *how much edge actually survives costs out-of-sample, and what the worst case is*, so
capital only goes to strategies that pass the bar.

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
| Strategy core | under active research (see plan.md) — moving toward evidence-based, risk-managed options strategies |
| Agent harness | written fresh, borrowing ml-intern patterns; multi-model via LiteLLM |
| Validation | out-of-sample / walk-forward + realistic costs, before any capital is risked |
| Cost control | fetch-size/cost guard + approval gating on expensive pulls |

## Quick start

Full setup (package + LLM + data sources) is in **[docs/INSTALL.md](docs/INSTALL.md)**.

```bash
uv sync --extra dev --extra data   # install
cp .env.example .env               # set OPTIONPILOT_DATA_SOURCE + keys (see INSTALL.md)
uv run optionpilot "回測 ZETA 近一年的賣 put 跟持股比"   # headless
uv run optionpilot                 # interactive
```

### Chat GUI

A Gradio chat interface that streams the intern's tool calls + verdict live:

```bash
uv sync --extra ui
bash scripts/serve_local.sh   # local model must be running (separate terminal)
uv run optionpilot-ui         # opens http://localhost:7860
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
  models/           XGBoost baseline strategy model
  backtest/         engine + metrics (Sharpe / MaxDD / WinRate / turnover)
  tracking/         experiment tracker (DuckDB)
```
