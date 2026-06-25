#!/usr/bin/env bash
# Set up OptionPilot on macOS — the Mac counterpart to setup_vllm.sh/serve_local.sh (NVIDIA-only,
# do NOT run those here). Picks an environment manager, installs the package into an isolated env,
# ASKS which LLM backend to use (default by chip), prompts for an API key on the cloud path,
# VERIFIES the LLM works with a tiny test request, and OPTIONALLY sets up options-desk data
# sources (Databento key / ThetaData: Java 21 + terminal jar — the perp desk & screener need none).
#
# Env manager priority:  uv (if present)  ->  conda (if present)  ->  ask: install uv | venv+pip
# Non-interactive (CI): -y / OPTIONPILOT_NONINTERACTIVE=1 uses the chip default, installs uv if
# neither uv nor conda exists, and skips the key prompt + verification.
# Secrets only land in .env / .env.* (all gitignored). Full guide: docs/deploy_mac.md
set -euo pipefail

cd "$(dirname "$0")/.."
ARCH="$(uname -m)"
MEM_GB=$(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1073741824 ))
echo "==> OptionPilot Mac setup  (arch: $ARCH, RAM: ${MEM_GB}GB)"

NONINTERACTIVE="${OPTIONPILOT_NONINTERACTIVE:-0}"
for arg in "$@"; do case "$arg" in -y|--yes) NONINTERACTIVE=1 ;; esac; done
[ -t 0 ] || NONINTERACTIVE=1     # no TTY (piped) -> can't prompt

# verify_llm <litellm-model>: send a tiny request and report whether the LLM is reachable/usable.
# Uses $RUN (set during env setup) so it works under uv / conda / venv. Reads provider keys from env.
verify_llm() {
  echo "==> 測試 LLM 是否可用(送一個極小請求)…"
  if $RUN python - "$1" <<'PY'
import sys, litellm
try:
    litellm.completion(model=sys.argv[1], messages=[{"role": "user", "content": "ping"}],
                       max_tokens=5)
    print("OK")
except Exception as e:  # noqa: BLE001
    print("FAIL: %s: %s" % (type(e).__name__, str(e)[:300]))
    sys.exit(1)
PY
  then echo "    ✅ LLM 可用"; return 0
  else echo "    ❌ 測試失敗(檢查 key / 額度 / 網路 / 模型名 / ollama serve 是否啟動)"; return 1; fi
}

# --- options-desk data-source helpers (append to $TARGET, which is set later) ---
append_env() { printf '%s\n' "$@" >> "$TARGET"; }

setup_databento_key() {
  read -r -s -p "    貼上 DATABENTO_API_KEY (db-...): " DBK; echo
  append_env "DATABENTO_API_KEY=${DBK}"
  echo "    ✅ Databento key 已寫入(Python SDK 已隨 --extra data 裝好)。"
}

install_thetadata() {
  if java -version 2>&1 | grep -q 'version "21'; then
    echo "    Java 21 已存在。"
  elif command -v brew >/dev/null 2>&1; then
    echo "==> brew install --cask temurin@21 …"
    brew install --cask temurin@21 || echo "!! Java 安裝失敗,請手動裝 JRE/JDK 21。"
  else
    echo "!! 沒有 Homebrew;請自行安裝 Java 21(temurin)。"
  fi
  local jar="$PWD/ThetaTerminalv3.jar"
  if [ -f "$jar" ]; then
    echo "    ThetaTerminalv3.jar 已存在。"
  else
    echo "==> 下載 ThetaTerminalv3.jar …"
    curl -fsSL -o "$jar" "https://download-unstable.thetadata.us/ThetaTerminalv3.jar" \
      || echo "!! 下載失敗,請手動從 download-unstable.thetadata.us 取得 ThetaTerminalv3.jar 放專案根。"
  fi
  append_env "OPTIONPILOT_THETADATA_URL=http://127.0.0.1:25503"
  read -r -p "    你的 ThetaData API key(td1_…,用來啟動終端,不會存檔): " THK
  echo "    ✅ 用資料前,另開一個終端執行並保持開著:"
  echo "        java -jar \"$jar\" --api-key ${THK:-td1_your_key}"
}

# --- pick an environment manager + install OptionPilot into an isolated env ---
HAS_UV=0;    if command -v uv >/dev/null 2>&1;    then HAS_UV=1;    fi
HAS_CONDA=0; if command -v conda >/dev/null 2>&1; then HAS_CONDA=1; fi
ENV_MODE=""

if [ "$NONINTERACTIVE" = "1" ]; then
  if   [ "$HAS_UV" = 1 ];    then ENV_MODE="uv"
  elif [ "$HAS_CONDA" = 1 ]; then ENV_MODE="conda"
  else                            ENV_MODE="install-uv"; fi
  echo "==> non-interactive env manager: $ENV_MODE"
else
  # default to what's already installed (uv > conda), else install uv — but always let you pick
  if [ "$HAS_UV" = 1 ]; then DEF=1; elif [ "$HAS_CONDA" = 1 ]; then DEF=2; else DEF=1; fi
  UVLBL="(未安裝 → 會自動裝)";   [ "$HAS_UV" = 1 ]    && UVLBL="(已安裝,推薦)"
  CDLBL="(未安裝 → 需先裝 miniforge)"; [ "$HAS_CONDA" = 1 ] && CDLBL="(已安裝)"
  echo
  echo "    用哪個環境管理器建立隔離環境?"
  echo "      1) uv $UVLBL"
  echo "      2) conda $CDLBL"
  echo "      3) venv + pip(需 Python 3.11+)"
  read -r -p "    請選 [$DEF]: " EM; EM="${EM:-$DEF}"
  case "$EM" in
    2) if [ "$HAS_CONDA" = 1 ]; then ENV_MODE="conda"
       else echo "!! 找不到 conda(請先裝 miniforge),或改選 1/3。" >&2; exit 1; fi ;;
    3) ENV_MODE="venv" ;;
    *) if [ "$HAS_UV" = 1 ]; then ENV_MODE="uv"; else ENV_MODE="install-uv"; fi ;;
  esac
fi

if [ "$ENV_MODE" = "install-uv" ]; then
  echo "==> 安裝 uv…"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  command -v uv >/dev/null 2>&1 || { echo "!! uv 裝好了但 PATH 還沒生效,重開終端再跑一次。" >&2; exit 1; }
  ENV_MODE="uv"
fi

RUN=""           # prefix for python/optionpilot calls
ACTIVATE_HINT=""  # what the user must run in their shell before calling optionpilot directly
case "$ENV_MODE" in
  uv)
    echo "==> uv sync --extra data --extra ui --extra dev"
    uv sync --extra data --extra ui --extra dev
    RUN="uv run"; ACTIVATE_HINT="" ;;
  conda)
    echo "==> conda env 'optionpilot' (python 3.12 + 預編 binary,繞過 wheel 問題)"
    # shellcheck disable=SC1091
    source "$(conda info --base)/etc/profile.d/conda.sh"
    conda env list | grep -q '^optionpilot ' \
      || conda create -y -n optionpilot python=3.12 pyarrow numpy scipy duckdb
    conda activate optionpilot
    pip install -e ".[data,ui,dev]"
    RUN=""; ACTIVATE_HINT="conda activate optionpilot" ;;
  venv)
    command -v python3 >/dev/null 2>&1 || { echo "!! 沒有 python3;改用 A) 裝 uv。" >&2; exit 1; }
    PYV="$(python3 -c 'import sys;print("%d%02d"%sys.version_info[:2])')"
    [ "$PYV" -ge 311 ] || { echo "!! 需要 Python 3.11+(目前 $PYV);改用 uv 或 conda。" >&2; exit 1; }
    echo "==> python3 -m venv .venv  +  pip install -e"
    python3 -m venv .venv
    # shellcheck disable=SC1091
    source .venv/bin/activate
    pip install -U pip >/dev/null
    pip install -e ".[data,ui,dev]"
    RUN=""; ACTIVATE_HINT="source .venv/bin/activate" ;;
esac
echo "==> 環境就緒($ENV_MODE)"

# --- choose the LLM backend (default by chip; ask unless non-interactive) ---
if [ "$ARCH" = "arm64" ]; then DEFAULT_CHOICE=1; else DEFAULT_CHOICE=2; fi
if [ "$NONINTERACTIVE" = "1" ]; then
  CHOICE="$DEFAULT_CHOICE"
  echo "==> non-interactive: using chip default (choice $CHOICE)"
else
  echo
  echo "    要用哪種 LLM backend?"
  echo "      1) 本地 Ollama(免費,Apple Silicon 建議;Intel 會很慢)"
  echo "      2) 雲端 API(DeepSeek / Anthropic,品質較好但需 key)"
  echo "      3) 跳過,我自己設定 .env"
  read -r -p "    請選 [$DEFAULT_CHOICE]: " CHOICE
  CHOICE="${CHOICE:-$DEFAULT_CHOICE}"
fi

# --- .env target (never overwrite an existing .env; all .env* are gitignored) ---
TARGET=".env"
if [ -f ".env" ]; then
  TARGET=".env.mac.example"
  echo "==> .env already exists — writing to $TARGET instead (gitignored; merge/rename when ready)."
fi

case "$CHOICE" in
  1)  # local Ollama (model size from RAM)
    if   [ "$MEM_GB" -ge 32 ]; then MODEL_TAG="qwen2.5-coder:32b"
    elif [ "$MEM_GB" -ge 16 ]; then MODEL_TAG="qwen2.5-coder:14b"
    else                            MODEL_TAG="qwen2.5-coder:7b"
    fi
    [ "$ARCH" = "arm64" ] || echo "!! Intel + local: CPU inference will be slow; cloud is recommended."
    echo "==> local Ollama -> ${MODEL_TAG}"
    {
      echo "# OptionPilot — local LLM via Ollama"
      echo "OPTIONPILOT_MODEL=ollama_chat/${MODEL_TAG}"
      echo "OPTIONPILOT_API_BASE=http://localhost:11434"
      echo "OPTIONPILOT_API_KEY=ollama"
    } > "$TARGET"
    if command -v ollama >/dev/null 2>&1; then
      echo "==> Pulling ${MODEL_TAG} (can take a while)…"
      ollama pull "${MODEL_TAG}" || echo "!! pull failed — run 'ollama pull ${MODEL_TAG}' manually."
    else
      echo "!! Ollama not installed: 'brew install ollama' (or https://ollama.com), then"
      echo "   ollama serve  &&  ollama pull ${MODEL_TAG}"
    fi
    if curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1; then
      verify_llm "ollama_chat/${MODEL_TAG}" || true
    else
      echo "==> Ollama 尚未回應 — 先 'ollama serve'(+ pull),再 'bash scripts/setup_mac.sh -y' 重驗。"
    fi
    ;;

  2)  # cloud (prompt for key + verify)
    if [ "$NONINTERACTIVE" = "1" ]; then
      echo "==> cloud (non-interactive): writing template with a blank key."
      {
        echo "# OptionPilot — cloud LLM (fill in ONE provider key)"
        echo "OPTIONPILOT_MODEL=deepseek/deepseek-chat"
        echo "DEEPSEEK_API_KEY="
        echo "# OPTIONPILOT_MODEL=anthropic/claude-sonnet-4-6"
        echo "# ANTHROPIC_API_KEY="
      } > "$TARGET"
      echo "!! Edit $TARGET, add your key, then verify with 'bash scripts/setup_mac.sh -y' or run optionpilot."
    else
      echo
      echo "    哪一家?  1) DeepSeek   2) Anthropic   3) 其他(手動)"
      read -r -p "    請選 [1]: " PROVIDER; PROVIDER="${PROVIDER:-1}"
      case "$PROVIDER" in
        2) MODEL="anthropic/claude-sonnet-4-6"; KEYVAR="ANTHROPIC_API_KEY" ;;
        3) MODEL=""; KEYVAR="" ;;
        *) MODEL="deepseek/deepseek-chat"; KEYVAR="DEEPSEEK_API_KEY" ;;
      esac
      if [ -z "$MODEL" ]; then
        echo "==> 其他供應商:請依 LiteLLM 文件手動設定 $TARGET(OPTIONPILOT_MODEL + 對應 key)。"
        { echo "# OptionPilot — cloud LLM (set model + provider key per LiteLLM docs)"
          echo "OPTIONPILOT_MODEL="; } > "$TARGET"
      else
        read -r -s -p "    貼上 ${KEYVAR}: " APIKEY; echo
        {
          echo "# OptionPilot — cloud LLM"
          echo "OPTIONPILOT_MODEL=${MODEL}"
          echo "${KEYVAR}=${APIKEY}"
        } > "$TARGET"
        export "${KEYVAR}=${APIKEY}"
        verify_llm "$MODEL" || echo "    (.env 已寫好;修正 key/額度後可重跑驗證。)"
      fi
    fi
    ;;

  *)  # skip
    echo "==> skipping .env — configure it yourself (see docs/deploy_mac.md §2/§3)."
    TARGET="(none)"
    ;;
esac

# --- optional: OPTIONS-desk data sources (perp desk / stock screener / VIX need NO key) ---
if [ "$NONINTERACTIVE" = "1" ]; then
  echo "==> 跳過選擇權資料源(非互動);需要時見 docs/deploy_mac.md §4。"
elif [ "$TARGET" != "(none)" ]; then
  echo
  echo "    要設定「選擇權」資料源嗎?(幣安永續台 / 選股 screener / VIX 都不需要 key)"
  echo "      1) 不用,跳過"
  echo "      2) Databento(深歷史,付費,雲端)"
  echo "      3) ThetaData(免費近2年,本地 Java 終端)"
  echo "      4) 兩個都設"
  read -r -p "    請選 [1]: " DSRC; DSRC="${DSRC:-1}"
  case "$DSRC" in
    2) append_env "" "# --- options data ---" "OPTIONPILOT_DATA_SOURCE=databento"
       setup_databento_key ;;
    3) append_env "" "# --- options data ---" "OPTIONPILOT_DATA_SOURCE=thetadata"
       install_thetadata ;;
    4) append_env "" "# --- options data ---" "OPTIONPILOT_DATA_SOURCE=thetadata"
       setup_databento_key; install_thetadata
       echo "    (兩者皆設;預設 thetadata,要改用 databento 就改 $TARGET 的 OPTIONPILOT_DATA_SOURCE)" ;;
    *) echo "==> 跳過資料源。需要選擇權真實 chain 時再設(docs/deploy_mac.md §4)。" ;;
  esac
fi

echo
[ "$TARGET" = "(none)" ] || echo "==> Wrote $TARGET"
echo "    Next:"
[ -n "$ACTIVATE_HINT" ] && echo "      • 先啟用環境:  $ACTIVATE_HINT"
echo "      • crypto desk (no data key):  ${RUN:+$RUN }optionpilot --profile crypto \"分析 NOKUSDT 資金費率\""
echo "      • options desk (needs data):  start ThetaData/Databento, then ${RUN:+$RUN }optionpilot \"...\""
echo "      • GUI (two tabs):             ${RUN:+$RUN }optionpilot-ui"
echo "    Full guide: docs/deploy_mac.md"
