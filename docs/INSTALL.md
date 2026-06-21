# OptionPilot — Installation & Setup

Full setup for the four pieces: the Python package, an LLM (local or hosted), and the data
sources (Databento and/or free ThetaData). Paths below match this machine
(`/media/user/data2/chiehchi/...`); adjust for another box.

## 0. Prerequisites

- **Python 3.11+** (this box: 3.13) and **uv** (`uv --version`).
- For the local LLM: an NVIDIA GPU + driver. This box: 2× RTX Pro 6000 (driver 570 = CUDA 12.8).
- For ThetaData: **Java 21** (the v3 terminal needs it; the system Java 8 is too old).

## 1. The Python package

```bash
cd /media/user/data2/chiehchi/project
uv sync --extra dev --extra data      # dev = pytest/ruff; data = databento/yfinance/requests
uv run pytest -q                      # sanity: all tests pass
cp .env.example .env                  # then edit .env (see below)
uv run optionpilot --version
```

`.env` keys (all gitignored):
```
OPTIONPILOT_DATA_SOURCE=thetadata        # or databento
OPTIONPILOT_MODEL=hosted_vllm/Qwen/Qwen3-Coder-30B-A3B-Instruct-FP8
OPTIONPILOT_API_BASE=http://localhost:8000/v1
OPTIONPILOT_API_KEY=local
DATABENTO_API_KEY=db-...                 # only if using databento
OPTIONPILOT_THETADATA_URL=http://127.0.0.1:25503
OPTIONPILOT_MAX_FETCH_USD=5.0            # Databento per-fetch cost guard
```

## 2. LLM — local (zero-cost) via vLLM

One-time venv build + per-session server (kept separate from the project venv):

```bash
bash scripts/setup_vllm.sh            # builds /media/user/data2/chiehchi/vllm-env (cu128 pins)
bash scripts/serve_local.sh           # serves Qwen3-Coder-30B FP8 on one Pro 6000 (port 8000)
```

Why the pins (encoded in the scripts): driver 570 = CUDA 12.8, so torch must be cu128 (the
default cu130 errors `libcudart.so.13`); that pins vLLM 0.11.0; transformers must be `<5`; and
FlashInfer's JIT sampler is disabled (system nvcc 12.2 can't compile Blackwell sm_120). See
`scripts/setup_vllm.sh` header for details.

> Alternative (no GPU): set `OPTIONPILOT_MODEL` to a hosted model (e.g. `deepseek/deepseek-v4-flash`)
> and put the provider key in `.env`; leave `OPTIONPILOT_API_BASE` empty.

## 3. Data source A — ThetaData (free, recent ~2yr, bid/ask + volume)

Best for cheap research of recently-liquid single stocks. Needs the **v3 terminal + Java 21**
(both already downloaded under `/media/user/data2/chiehchi/thetadata/`). Full details +
free-tier limits: [thetadata_setup.md](thetadata_setup.md). Quick version:

```bash
cd /media/user/data2/chiehchi/thetadata
export JAVA_HOME=/media/user/data2/chiehchi/thetadata/jdk-21.0.11+10-jre
export PATH=$JAVA_HOME/bin:$PATH
java -jar ThetaTerminalv3.jar --api-key td1_your_key   # wait for "Starting server at ...:25503"
```
Then `OPTIONPILOT_DATA_SOURCE=thetadata` in `.env`. (To rebuild from scratch: download
`ThetaTerminalv3.jar` from download-unstable.thetadata.us and a Temurin JRE 21.)

## 4. Data source B — Databento (any ticker, deep history, per-GB)

For tickers/history ThetaData's free tier lacks. Put `DATABENTO_API_KEY` in `.env` and set
`OPTIONPILOT_DATA_SOURCE=databento`. Fetches are cost-estimated and guarded by
`OPTIONPILOT_MAX_FETCH_USD`; you approve each real download. New signups get $125 free credit.

## 5. Run

```bash
# terminal 1: LLM server (if local)      -> bash scripts/serve_local.sh
# terminal 2: ThetaData terminal (if used)-> java -jar ThetaTerminalv3.jar --api-key ...
# terminal 3:
uv run optionpilot "回測 ZETA 近一年的賣 cash-secured put,跟買進持有比"   # headless
uv run optionpilot                                                      # interactive
```

Reports are auto-saved to `runs/` and logged to `runs/experiments.duckdb`.
