# OptionPilot

An autonomous **derivatives-strategy research agent** — think of it as an *ML intern* that
researches strategies for you. Given a natural-language task it runs the full research loop
itself (fetch data → analyze → backtest → read metrics → iterate → honest verdict) and proves
every claim with rigorous out-of-sample backtesting instead of asking you to trust a black box.

It has **two isolated research desks** sharing one agent core (separate prompt, playbook, tools,
and conversation context — they never mix):

| Desk | `--profile` | Universe | Data (public/free first) | What it researches |
|---|---|---|---|---|
| **股票期權** | `options` | US equity options | ThetaData (free) / Databento (paid) + yfinance | VRP screening, cash-secured-put / covered-call / wheel backtests, walk-forward, unusual activity, charts, support/resistance |
| **幣安永續** | `crypto` | Binance USDⓈ-M perps (incl. US-stock perps like NOKUSDT/AAPLUSDT) | `fapi.binance.com` public REST (no key) | funding-rate carry (the perp analog of VRP), grid-bot backtest |

The perp desk uses **public market data only — no API key, no order placement**: it analyzes and
backtests, it does not trade.

> 📐 Full architecture (layered diagram, agent-loop sequence, per-desk data flow, module
> reference): **[docs/architecture.md](docs/architecture.md)**.

## Goal

OptionPilot stands on two pillars:

1. **An ml-intern-style autonomous research loop.** Give it a task — "research cash-secured puts
   on ZETA" or "is a grid bot worth running on NOKUSDT?" — and it runs the experiment loop
   itself: propose a hypothesis → fetch data → analyze → backtest → read metrics → propose the
   next improvement → iterate → deliver the best strategy with a full, honest experiment log. It
   proposes, iterates, and records on its own (`ExperimentLoop` + `Planner` + `ExperimentTracker`).

2. **A rigorous, verifiable backtesting system.** Every strategy must pass the same honest bar:
   out-of-sample / walk-forward evaluation, realistic costs (spread, slippage, fees, assignment,
   funding), full metrics (Sharpe, max drawdown, win rate, turnover) plus worst-case stress
   tests, reproducible head-to-head run comparison, and honest reporting of negative results.

The same methodology runs on **both desks**. The options desk screens variance risk premium and
backtests put/call selling; the perp desk treats the funding rate as the structural analog of VRP
and stress-tests grid bots — separating booked grid profit from stuck-inventory loss, and showing
how a grid bleeds in a trend. Both always benchmark against simply buying & holding.

**Success** is not "find a magic money signal" — it's being able to answer, for any candidate
strategy, *how much edge actually survives costs out-of-sample, and what the worst case is*, so
capital only goes to strategies that pass the bar.

> Architecture borrows patterns from [huggingface/ml-intern](https://github.com/huggingface/ml-intern)
> (agentic loop, ContextManager, ToolRouter, approval gating, doom-loop detection) but is written
> fresh with no Hugging Face coupling, specialized for options & perpetual-futures research.

## Status

Early scaffold. See [plan.md](plan.md) for the full design and roadmap.

## Key design decisions

| Area | Choice |
|---|---|
| Options data | ThetaData free tier (local terminal, recent ~2yr, real bid/ask + volume) as default; Databento OPRA (deep history, pay-as-you-go) for older tickers; greeks computed locally |
| Perp data | Binance USDⓈ-M public REST (`fapi.binance.com`) — klines, funding rate, open interest, long/short ratio; no API key |
| Desk isolation | two profiles (`options` / `crypto`) with separate prompt, playbook, tools, and context — `agent/profiles.py` |
| Agent harness | written fresh, borrowing ml-intern patterns; multi-model via LiteLLM |
| Validation | out-of-sample / walk-forward + realistic costs (spread, slippage, fees, funding) before any capital is risked |
| Cost control | fetch-size/cost guard + approval gating on expensive (Databento) pulls |

## Quick start

Full setup (package + LLM + data sources) is in **[docs/INSTALL.md](docs/INSTALL.md)**.

```bash
uv sync --extra dev --extra data   # install
cp .env.example .env               # set OPTIONPILOT_DATA_SOURCE + keys (see INSTALL.md)

# options desk (default)
uv run optionpilot "回測 ZETA 近一年的賣 put 跟持股比"
# perp desk — public Binance data, no key needed
uv run optionpilot --profile crypto "分析 NOKUSDT 的資金費率 carry，並回測網格"
uv run optionpilot                 # interactive (add --profile crypto for the perp desk)
```

### Chat GUI

A Gradio app with **two tabs** (股票期權 / 幣安永續), each its own isolated session, streaming the
agent's tool calls + verdict live and showing charts inline:

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

See **[docs/architecture.md](docs/architecture.md)** for the full picture; in brief:

```
optionpilot/
  cli.py            Typer entry (interactive / headless, --profile options|crypto)
  config.py         config hierarchy (env > defaults)
  ui/app.py         Gradio GUI — two isolated desks as tabs
  llm/              LiteLLM client wrapper (local vLLM / cloud)
  agent/            loop, context, router, doom-loop, approval, planner,
                    playbook (options + crypto), profiles (desk isolation), lang (繁體)
  tools/            options: measure_vrp, run_backtest, optimize_strategy,
                    detect_unusual_activity, make_charts, support_resistance, fetch_options_data
                    crypto:  funding_analysis, grid_backtest
                    shared:  ask_user, list_experiments
  analysis.py       VRP (implied vs realized, up/down split) + support/resistance
  crypto.py         perp funding summary (carry) + realized vol from klines
  data/             sources (ThetaData/Databento ABC), market loaders, databento fetcher
                    (+ cost guard), osi parser, binance public client, Black-Scholes greeks
  backtest/         strategies (CSP/CC/wheel), grid (perp grid bot), walkforward, metrics
  signals/          unusual options activity + put/call flow
  plots.py          matplotlib charts (CJK 繁體)
  tracking/         experiment tracker (DuckDB) + Markdown reports
```
