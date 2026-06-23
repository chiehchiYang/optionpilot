#!/usr/bin/env bash
# Set up OptionPilot on macOS — the Mac counterpart to setup_vllm.sh/serve_local.sh (which are
# NVIDIA-only and must NOT be run here). It runs `uv sync`, ASKS which LLM backend to use
# (defaulting by chip), prompts for an API key when you pick cloud, writes a `.env`, and then
# VERIFIES the LLM works with a tiny test request.
#
#   Apple Silicon (arm64): default = local Ollama (Metal); model size chosen from RAM.
#   Intel (x86_64):        default = cloud (local CPU inference isn't worth it).
#
# Non-interactive (CI): pass -y/--yes or set OPTIONPILOT_NONINTERACTIVE=1 to use the chip default
# and skip the key prompt + verification. Secrets only land in .env / .env.* (all gitignored).
# Full guide: docs/deploy_mac.md
set -euo pipefail

cd "$(dirname "$0")/.."
ARCH="$(uname -m)"
MEM_GB=$(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1073741824 ))
echo "==> OptionPilot Mac setup  (arch: $ARCH, RAM: ${MEM_GB}GB)"

# --- prerequisites (check, don't force-install) ---
if ! command -v python3 >/dev/null 2>&1; then
  echo "!! Python 3.11+ not found. Install it (brew install python@3.12) and re-run." >&2; exit 1
fi
echo "    Python $(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
if ! command -v uv >/dev/null 2>&1; then
  echo "!! 'uv' not found. Install:  curl -LsSf https://astral.sh/uv/install.sh | sh   (then re-run)" >&2
  exit 1
fi

# verify_llm <litellm-model>: send a tiny request and report whether the LLM is reachable/usable.
# Reads provider keys from the environment (export them before calling). Returns non-zero on fail.
verify_llm() {
  echo "==> 測試 LLM 是否可用(送一個極小請求)…"
  if uv run python - "$1" <<'PY'
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

# --- python package ---
echo "==> uv sync --extra data --extra ui --extra dev"
uv sync --extra data --extra ui --extra dev

# --- choose the LLM backend (default by chip; ask unless non-interactive) ---
if [ "$ARCH" = "arm64" ]; then DEFAULT_CHOICE=1; else DEFAULT_CHOICE=2; fi
NONINTERACTIVE="${OPTIONPILOT_NONINTERACTIVE:-0}"
for arg in "$@"; do case "$arg" in -y|--yes) NONINTERACTIVE=1 ;; esac; done
[ -t 0 ] || NONINTERACTIVE=1     # no TTY (piped) -> can't prompt

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
      echo "OPTIONPILOT_DATA_SOURCE=thetadata"
      echo "# DATABENTO_API_KEY=db-..."
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
        echo "OPTIONPILOT_DATA_SOURCE=thetadata"
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
        {
          echo "# OptionPilot — cloud LLM (set your model + provider key per LiteLLM docs)"
          echo "OPTIONPILOT_MODEL="
          echo "OPTIONPILOT_DATA_SOURCE=thetadata"
        } > "$TARGET"
      else
        read -r -s -p "    貼上 ${KEYVAR}: " APIKEY; echo
        {
          echo "# OptionPilot — cloud LLM"
          echo "OPTIONPILOT_MODEL=${MODEL}"
          echo "${KEYVAR}=${APIKEY}"
          echo "OPTIONPILOT_DATA_SOURCE=thetadata"
          echo "# DATABENTO_API_KEY=db-..."
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

echo
[ "$TARGET" = "(none)" ] || echo "==> Wrote $TARGET"
echo "    Next:"
echo "      • crypto desk (no data key):  uv run optionpilot --profile crypto \"分析 NOKUSDT 資金費率\""
echo "      • options desk (needs data):  start ThetaData/Databento, then uv run optionpilot \"...\""
echo "      • GUI (two tabs):             uv run optionpilot-ui"
echo "    Full guide: docs/deploy_mac.md"
