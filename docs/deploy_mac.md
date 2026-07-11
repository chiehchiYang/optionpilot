# OptionPilot — 部署到 Mac(Intel / Apple Silicon)

整個專案幾乎完全可攜:Python 套件、ThetaData 終端(Java)、Databento / Binance / yfinance、
Gradio GUI 在 Mac 上都照跑。**唯一不能搬的是本地 vLLM 服務(需要 NVIDIA/CUDA)** ——
所以「部署到 Mac」本質上只有一件事:**換掉 LLM backend**,其餘照 [INSTALL.md](INSTALL.md) 走。

LLM 早已抽象成 LiteLLM([llm/client.py](../optionpilot/llm/client.py)),只靠三個環境變數切換:
`OPTIONPILOT_MODEL` / `OPTIONPILOT_API_BASE` / `OPTIONPILOT_API_KEY`。

---

## 一鍵起步

```bash
bash scripts/setup_mac.sh          # 互動:檢查環境、uv sync,然後「問你」要哪種 LLM
bash scripts/setup_mac.sh -y       # 非互動:直接用依晶片的預設(CI/自動化;也可 OPTIONPILOT_NONINTERACTIVE=1)
```
**環境管理器**(不一定要有 uv):腳本會讓你**從三項挑一個**建立隔離環境 ——

```
用哪個環境管理器建立隔離環境?
  1) uv      (已安裝,推薦 / 未安裝→會自動裝)
  2) conda   (已安裝 / 未安裝→需先裝 miniforge;最能繞過舊 macOS 的 wheel 問題)
  3) venv + pip(需 Python 3.11+)
請選 [預設]:
```

預設值依現況(已裝 uv→1、否則已裝 conda→2、都沒有→1 自動裝 uv),但**永遠可手動改** ——
例如本機同時有 conda 和 uv 也能選 1 用 uv,或選 2 用 conda。非互動 `-y` 模式則自動取
uv→conda→裝 uv。三種都是建隔離環境裝套件,差別只在工具;之後啟動指令會跟著切換(uv 用
`uv run optionpilot`;conda/venv 先啟用環境再 `optionpilot`,腳本最後會印出該下哪一行)。

它會偵測晶片(`arm64` vs `x86_64`)與 RAM、備妥環境,接著**問你要哪種 LLM
backend**(預設依晶片:Apple Silicon→本地 Ollama、Intel→雲端):

```
要用哪種 LLM backend?
  1) 本地 Ollama(免費,Apple Silicon 建議;Intel 會很慢)
  2) 雲端 API(DeepSeek / Anthropic,品質較好但需 key)
  3) 跳過,我自己設定 .env
請選 [1]:
```

選好後:
- **雲端**:再問你是哪家(DeepSeek/Anthropic),**提示你貼上 API key**(輸入隱藏),寫進 `.env`。
- **本地**:依 RAM 自動選 7b/14b/32b,偵測到 Ollama 就幫你 `pull`。
- **接著實測**:送一個極小請求**驗證 LLM 是否真的可用**(`✅ 可用` / `❌ 失敗 + 原因`)。

安全性:所有 `.env*` 都已 gitignore(只有範本 `.env.example` 仍追蹤),key 不會被 commit;
且**不覆蓋既有 `.env`**(改寫 `.env.mac.example`)。下面是各路徑的細節與理由。

---

## 1. 決策:本地模型還是雲端?

| | Apple Silicon(M1/M2/M3…) | 舊 Intel Mac |
|---|---|---|
| 本地跑 LLM | ✅ 可,Metal GPU + 統一記憶體,用 **Ollama** | ⚠️ 只能 CPU、非常慢,**不建議** |
| 建議 | **Ollama 跑量化 Qwen Coder**(依 RAM 選大小);追求品質可改雲端 | **雲端 API**(DeepSeek/Anthropic),零本地算力 |

**為什麼**:agentic 迴圈一輪要連續呼叫多個工具(measure_vrp → 回測 → walk-forward …),
需要可靠的 tool-calling。Apple Silicon 的 Metal 能跑量化模型;舊 Intel 無可用 GPU,本地推論
會慢到不堪用,雲端才務實。

---

## 2. 路徑 A — Apple Silicon + Ollama(本地、免費)

```bash
# 1) 安裝 Ollama(任一)
brew install ollama            # 或到 https://ollama.com 下載 App
ollama serve                   # 另一個終端,常駐

# 2) 依 RAM 拉一個 Qwen Coder(Q4 量化,粗估):
#    7B≈5GB(快) | 14B≈9GB(16GB 機可) | 32B≈20GB(需 32GB+、較慢)
ollama pull qwen2.5-coder:14b  # 用 `ollama list` 看本機已有的;有新版 qwen coder 可換

# 3) 裝專案
uv sync --extra data --extra ui
```

`.env`:
```
OPTIONPILOT_MODEL=ollama_chat/qwen2.5-coder:14b   # ollama_chat 走 /api/chat,tool calling 較穩
OPTIONPILOT_API_BASE=http://localhost:11434
OPTIONPILOT_API_KEY=ollama
OPTIONPILOT_DATA_SOURCE=thetadata                 # 期權台才需要;幣安永續台不用任何 key
```

> **模型越小,多工具編排越弱**。7B 可能在連續工具呼叫上吃力;14B 起較穩。若某模型回報不支援
> tools,換一個支援 function calling 的(Qwen Coder 系列支援)。

---

## 3. 路徑 B — Intel Mac(或任何 Mac)+ 雲端(最務實)

不需要 GPU、不需要本地伺服器。

```bash
uv sync --extra data --extra ui
```
`.env`(擇一供應商,把對應 key 填上,`OPTIONPILOT_API_BASE` 留空):
```
OPTIONPILOT_MODEL=deepseek/deepseek-chat     # 或 anthropic/claude-sonnet-4-6 等
DEEPSEEK_API_KEY=sk-...                        # Anthropic 則用 ANTHROPIC_API_KEY
OPTIONPILOT_DATA_SOURCE=thetadata
```
LiteLLM 會依 model 前綴自動找對應的 provider key。

**或用 OpenCode Go(一個訂閱、多種模型,$10/月)** —— 可攜的 OpenAI 相容 key,無 GPU:
```
OPTIONPILOT_MODEL=openai/<go-的模型id>          # 例:deepseek-v4-pro / qwen3.7-max
OPTIONPILOT_API_BASE=https://opencode.ai/zen/go/v1
OPTIONPILOT_API_KEY=<你的 OpenCode Go API key>
```
- key:opencode.ai → Zen → 訂閱 **Go** → 複製;模型 **id 要一字不差**,到
  `https://opencode.ai/zen/go/v1/models` 查實際 slug。
- OptionPilot 重度用 tool-calling → 選會 function calling 的模型(DeepSeek V4 Pro / Qwen3.7 /
  Kimi K2.7 Code…);$10/月有用量上限,密集研究可能撞限。

---

## 4. 資料來源(哪些功能需要 key)

**多數功能不需要任何資料 key** —— 只有「選擇權真實 chain 回測」才需要 ThetaData 或 Databento:

| 功能 | 需要的資料 key |
|---|---|
| 幣安永續台(funding / 網格回測) | 無(公開 API `fapi.binance.com`,不下單) |
| 選股 screener / 多維分析 | 無(yfinance) |
| 市場情緒 VIX | 無(yfinance) |
| **選擇權回測**(CSP / covered call / wheel…) | **ThetaData 或 Databento(擇一)** |

> **`setup_mac.sh` 可以幫你裝這兩個**:跑到「要設定選擇權資料源嗎?」時選 Databento(輸入 key)、
> ThetaData(自動 `brew` 裝 Java 21 + 下載 `ThetaTerminalv3.jar` + 給你啟動指令),或兩者。
> 只玩永續台 / screener 就選「跳過」。手動步驟如下:

- **ThetaData**(免費,近 ~2yr):需 **Java 21** + v3 終端,Mac 可跑。
  ```bash
  brew install --cask temurin@21              # 或任何 JRE/JDK 21
  java -jar ThetaTerminalv3.jar --api-key td1_your_key   # 等 "Starting server at ...:25503"
  ```
  然後 `OPTIONPILOT_DATA_SOURCE=thetadata`。細節見 [thetadata_setup.md](thetadata_setup.md)。
- **Databento**(深歷史、付費):`DATABENTO_API_KEY=db-...` + `OPTIONPILOT_DATA_SOURCE=databento`;
  有 `OPTIONPILOT_MAX_FETCH_USD` 成本守門。SDK 已隨 `--extra data` 裝好。

---

## 5. 執行

```bash
# (Apple Silicon 本地模型) 終端 1:ollama serve
# (期權免費資料)         終端 2:java -jar ThetaTerminalv3.jar --api-key ...
# 終端 3:
uv run optionpilot --profile crypto "分析 NOKUSDT 的資金費率,並回測網格"   # 幣安永續台
uv run optionpilot "回測 ZETA 近一年的賣 cash-secured put,跟買進持有比"    # 期權台
uv run optionpilot-ui                                                      # GUI(兩個分頁)
```
報告存到 `runs/`、回測記錄進 `runs/experiments.duckdb`、研究路徑進 `runs/trajectories/`。

---

## 6. 疑難排解

- **舊 macOS 裝不了套件(pip 想從原始碼編 pyarrow/numpy/scipy/duckdb)**:舊系統可能沒有對應
  wheel。對策:① 升級到夠新的 macOS;② 改用 **miniforge/conda**(`conda install pyarrow numpy
  scipy duckdb`,有 osx-64 / osx-arm64 build);③ 把那幾個套件釘到較舊相容版本。這是舊 Intel 機
  最常卡的點,**與 LLM 無關**。
- **Apple Silicon 別裝到 x86 Python**:確認 `python3 -c "import platform; print(platform.machine())"`
  顯示 `arm64`(若顯示 `x86_64` 表示在 Rosetta 下,套件會用 Intel wheel、Metal 也用不到)。
- **Ollama 模型不支援 tools**:換一個支援 function calling 的模型;確認用的是 `ollama_chat/` 前綴。
- **記憶體不足/很慢**:換更小的量化模型(14B→7B),或改走雲端。
- **port 衝突**:Ollama 預設 11434、Gradio 7860、ThetaData 25503,被占用就改埠或關掉占用程式。
- **`OSError: [Errno 24] Too many open files`(頁面載不齊/壞掉)**:macOS 預設開檔上限只有 256,
  Gradio 送一堆前端資產就爆。`optionpilot-ui` 啟動時已會**自動拉高**;若仍遇到,啟動前手動:
  `ulimit -n 8192`(要跟 `uv run optionpilot-ui` 在同一個終端)。
- **matplotlib 中文**:已用 Agg backend;圖表中文字型會**自動偵測**跨平台 CJK 字型(macOS 內建的
  PingFang/Heiti、Linux 的 Noto CJK…)。若圖表中文變**亂碼/方框**:代表沒偵測到字型 —— macOS 通常內
  建 PingFang(直接可用);萬一沒有,清 matplotlib 快取重試:`rm -rf ~/.matplotlib ~/.cache/matplotlib`
  後重啟 UI。Linux 機請 `apt install fonts-noto-cjk` 再清快取。

---

## 7. 不要在 Mac 上做的事

`scripts/setup_vllm.sh` 與 `scripts/serve_local.sh` 是 **NVIDIA/CUDA 專用**(Blackwell/cu128 釘版),
Mac 上**不要執行**。Mac 用 `scripts/setup_mac.sh` 取代它們。

---

## 8. 已裝好的機器,如何更新

是 editable 安裝,**純程式碼改動 `git pull` 完即生效、不用重裝**。不必再跑一次 `setup_mac.sh`。

```bash
cd /path/to/optionpilot
git pull
# 依環境管理器重新同步相依(只有 pyproject 改了才需要,但跑一下最保險、沒變更就是 no-op):
uv sync --extra data --extra ui                                # uv
# 或：source .venv/bin/activate && pip install -e ".[data,ui]"     # venv
# 或：conda activate optionpilot && pip install -e ".[data,ui]"    # conda
```

**你的設定與資料不會被動到**(都在 `.gitignore`):`.env`(key)、`runs/`(實驗紀錄 / trajectories /
跨 session 記憶)、`data_cache/`。所以更新很安全。UI/agent 若開著,**Ctrl-C 後重開**才會載到新程式碼;
本地 Ollama 不受影響、不用動。若你改過被追蹤的檔案導致 pull 衝突:`git stash` → `git pull` →
`git stash pop`。
