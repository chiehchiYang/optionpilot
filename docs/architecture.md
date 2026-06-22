# OptionPilot 架構圖

OptionPilot 是一個自主研究 agent(「期權/永續的 ML intern」),用本地 LLM(Qwen)依循嚴謹、誠實的回測方法論研究策略。專案有**兩個互相隔離的研究台**,共用同一套 agent 核心:

| 研究台 | profile | 標的 | 資料來源 | 主要工具 |
|---|---|---|---|---|
| **股票期權** | `options` | 美股期權 | ThetaData(免費)/ Databento(付費)+ yfinance | VRP 篩選、CSP/CC/wheel 回測、walk-forward、異常活動、圖表、支撐壓力 |
| **幣安永續** | `crypto` | Binance USDⓈ-M 永續(含美股永續 NOKUSDT/AAPLUSDT…) | `fapi.binance.com` 公開資料(免 key) | 資金費率 carry 分析、網格回測 |

兩台各自擁有獨立的 system prompt、playbook、工具集與對話 context,**永不混用**(見 `agent/profiles.py`)。

---

## 1. 分層架構

```mermaid
flowchart TD
    subgraph Entry["入口 Entry points"]
        CLI["cli.py · Typer CLI<br/>--profile options|crypto"]
        UI["ui/app.py · Gradio<br/>兩個分頁 Tabs"]
    end

    subgraph Prof["隔離層 · agent/profiles.py"]
        BL["build_loop(config, profile)"]
        OPT(["OPTIONS_PROFILE<br/>股票期權"])
        CRY(["CRYPTO_PROFILE<br/>幣安永續"])
        BL --> OPT
        BL --> CRY
    end

    CLI --> BL
    UI --> BL

    subgraph Core["Agent 核心 · agent/"]
        LOOP["ExperimentLoop · loop.py<br/>agentic loop"]
        CTX["ContextManager · context.py<br/>(壓縮/截斷)"]
        DOOM["DoomLoopDetector<br/>doom_loop.py"]
        ROUTER["ToolRouter · router.py<br/>dispatch + schema"]
        PB["playbook.py<br/>RESEARCH / CRYPTO_PLAYBOOK"]
        LANG["lang.py · OpenCC 繁體"]
        APPR["approval.py · 花費守門"]
        PLAN["planner.py · Planner<br/>(自主下一步)"]
    end

    OPT --> LOOP
    CRY --> LOOP
    LOOP --> CTX
    LOOP --> DOOM
    LOOP --> ROUTER
    LOOP -. 繁體輸出 .-> LANG
    LOOP --> LLM

    subgraph LLMl["LLM"]
        LLM["llm/client.py · LiteLLM"]
        VLLM["本地 vLLM<br/>Qwen3-Coder-30B-FP8<br/>(或雲端模型)"]
        LLM --> VLLM
    end

    ROUTER --> TOOLS

    subgraph TOOLS["工具層 · tools/ (ToolSpec)"]
        direction LR
        subgraph OptT["options 工具集"]
            T1["measure_vrp"]
            T2["run_backtest"]
            T3["optimize_strategy"]
            T4["detect_unusual_activity"]
            T5["make_charts"]
            T6["support_resistance"]
            T7["fetch_options_data"]
        end
        subgraph CryT["crypto 工具集"]
            C1["funding_analysis"]
            C2["grid_backtest"]
        end
        subgraph Sh["共用"]
            S1["ask_user"]
            S2["list_experiments"]
        end
    end

    OptT --> DOM_O
    CryT --> DOM_C

    subgraph DOM_O["期權領域邏輯"]
        A1["analysis.py · VRP/支撐壓力"]
        A2["backtest/strategies.py<br/>CSP·CC·wheel"]
        A3["backtest/walkforward.py"]
        A4["backtest/metrics.py"]
        A5["signals/unusual_activity.py"]
        A6["plots.py · 圖表(CJK)"]
        A7["data/greeks.py · Black-Scholes"]
    end

    subgraph DOM_C["永續領域邏輯"]
        B1["crypto.py · funding_summary<br/>realized_vol"]
        B2["backtest/grid.py · 網格引擎"]
    end

    DOM_O --> DATA_O
    DOM_C --> DATA_C

    subgraph DATA_O["期權資料層"]
        M["data/market.py · loaders"]
        SRC["data/sources.py<br/>OptionDataSource ABC"]
        TD["ThetaDataSource"]
        DB["DatabentoSource"]
        FET["data/databento_fetcher.py<br/>(成本守門)"]
        OSI["data/osi.py · OSI 解析"]
        YF["yfinance · underlying"]
        M --> SRC --> TD
        SRC --> DB --> FET
    end

    subgraph DATA_C["永續資料層"]
        BN["data/binance.py<br/>klines/funding/OI/多空比<br/>公開 fapi,免 key"]
    end

    T2 --> TRACK
    T3 --> TRACK
    subgraph TR["追蹤"]
        TRACK["tracking/experiment_tracker.py<br/>DuckDB · 每次回測一列"]
        REP["tracking/report.py · Markdown 報告"]
    end

    CFG["config.py · Config(env>預設)"]:::cfg
    CFG -.-> Core
    CFG -.-> DATA_O
    CFG -.-> DATA_C

    classDef cfg fill:#f5f5dc,stroke:#999;
```

---

## 2. Agent loop 執行流程

`ExperimentLoop.run(task)`(`agent/loop.py`)的單回合循環,借用 ml-intern 的結構:

```mermaid
sequenceDiagram
    participant U as 使用者
    participant L as ExperimentLoop
    participant C as ContextManager
    participant LLM as LLMClient(LiteLLM)
    participant D as DoomLoopDetector
    participant R as ToolRouter
    participant T as 工具(ToolSpec)

    U->>L: run(task)
    L->>C: add(user, task)
    loop 直到無 tool call 或達 max_iterations
        L->>C: 需要時壓縮 context
        L->>LLM: complete(messages, tools=schemas)
        LLM-->>L: assistant 訊息(可能含 tool_calls)
        alt 沒有 tool_calls
            L->>L: to_traditional(回覆) 繁體轉換
            L-->>U: 最終答覆
        else 有 tool_calls
            loop 每個 tool call
                L->>D: record(name, args) 重複偵測
                alt 偵測到迴圈
                    D-->>L: 注入糾正、跳過
                else 正常
                    L->>R: dispatch(name, args)
                    R->>T: handler(**args)
                    T-->>R: 結果(JSON/數據)
                    R-->>L: 結果
                end
                L->>C: add(tool, 結果)
            end
        end
    end
```

> 花費守門:只有付費下載(Databento)會經 `approval.py`;估價/快取命中不收費也不詢問。GUI 用 `auto_spend`、CLI 互動模式用 `interactive_spend`(無 TTY 時預設拒絕,避免靜默花錢)。

---

## 3. 兩個研究台的資料流(隔離)

```mermaid
flowchart LR
    subgraph OPTIONS["股票期權 desk"]
        direction TB
        oq["問題:某美股期權策略"] --> oloop["ExperimentLoop<br/>(OPTIONS_PROFILE)"]
        oloop --> ovrp["measure_vrp"] --> oa["analysis.py"]
        oloop --> obt["run_backtest"] --> ost["strategies.py"]
        oloop --> owf["optimize_strategy"] --> owff["walkforward.py"]
        oa --> omkt["market.py → sources.py"]
        ost --> omkt
        omkt --> otd["ThetaData / Databento"]
        omkt --> oyf["yfinance underlying"]
        obt --> otrk["DuckDB tracker + 報告"]
    end

    subgraph CRYPTO["幣安永續 desk"]
        direction TB
        cq["問題:某永續 funding/網格"] --> cloop["ExperimentLoop<br/>(CRYPTO_PROFILE)"]
        cloop --> cfa["funding_analysis"] --> ccr["crypto.py funding_summary"]
        cloop --> cgb["grid_backtest"] --> cgrid["backtest/grid.py"]
        ccr --> cbn["data/binance.py(公開 fapi)"]
        cgrid --> cbn
    end

    OPTIONS -. 不共用 context/工具/prompt .- CRYPTO
```

---

## 4. 模組速查

| 路徑 | 角色 |
|---|---|
| `cli.py` | Typer CLI;`--profile` 選研究台,互動/headless 兩種模式 |
| `ui/app.py` | Gradio GUI;`gr.Tabs` 兩分頁,各自獨立 session,工具呼叫即時串流、圖表 inline |
| `config.py` | `Config`(env > 預設):模型、api_base、資料源、花費上限、快取/runs 目錄 |
| **agent/** | |
| `agent/profiles.py` | `Profile` 抽象 + `OPTIONS_PROFILE`/`CRYPTO_PROFILE` + `build_loop()` 工廠 |
| `agent/loop.py` | `ExperimentLoop` agentic 迴圈;兩套 system prompt |
| `agent/context.py` | `ContextManager`:對話歷史 + token 壓縮 |
| `agent/doom_loop.py` | `DoomLoopDetector`:偵測重複 tool 呼叫並糾正 |
| `agent/router.py` | `ToolRouter`:工具註冊、OpenAI schema 匯出、dispatch |
| `agent/planner.py` | `Planner`:自主提出下一步實驗(LLM + JSON) |
| `agent/playbook.py` | `RESEARCH_PLAYBOOK`(期權)/ `CRYPTO_PLAYBOOK`(永續)方法論 |
| `agent/lang.py` | `to_traditional()`:OpenCC s2twp 簡→繁 |
| `agent/approval.py` | 付費下載的花費守門(auto / interactive) |
| **llm/** | |
| `llm/client.py` | LiteLLM 薄包裝;本地 vLLM 或雲端模型皆可 |
| **tools/** | |
| `tools/base.py` | `ToolSpec` 契約 + OpenAI function schema |
| `tools/__init__.py` | `OPTIONS_BUILDERS` / `CRYPTO_BUILDERS` 分組 + `build_tools` |
| `tools/*.py` | 各工具:measure_vrp / run_backtest / optimize_strategy / detect_unusual_activity / make_charts / support_resistance / fetch_options_data / **funding_analysis** / **grid_backtest** / ask_user / list_experiments |
| **領域邏輯** | |
| `analysis.py` | VRP(隱含 vs 實現波動,上/下行分離)、支撐壓力 |
| `crypto.py` | 永續 funding 摘要(年化、誰付誰、carry 方向)、K 線實現波動 |
| `backtest/strategies.py` | CSP / covered call / wheel 回測(真實 bid/ask 成交、成本) |
| `backtest/grid.py` | 長倉網格引擎(已實現格利 vs 套牢、跌穿區間、含 funding 拖累) |
| `backtest/walkforward.py` | walk-forward 最佳化(防過擬合) |
| `backtest/metrics.py` | sharpe / max drawdown / win rate / 摘要 |
| `signals/unusual_activity.py` | 異常期權活動 + put/call flow |
| `plots.py` | matplotlib 圖表(Agg、Noto CJK TC 繁體標題) |
| `data/greeks.py` | Black-Scholes 定價 + 隱含波動率求解 |
| **資料層** | |
| `data/market.py` | tools 用的 loaders(期權鏈 + underlying) |
| `data/sources.py` | `OptionDataSource` ABC + ThetaData/Databento 實作 + 正規化 schema |
| `data/databento_fetcher.py` | Databento 下載 + 成本守門(`CostGuardError`/`FetchDenied`) |
| `data/osi.py` | OSI 期權代碼解析 |
| `data/binance.py` | Binance USDⓈ-M 公開資料(klines/funding/OI/多空比),免 key |
| **追蹤** | |
| `tracking/experiment_tracker.py` | DuckDB,每次回測存一列供比較 |
| `tracking/report.py` | 回測 Markdown 報告 |

> **Phase-2 佔位(尚未接線)**:`backtest/engine.py`(訊號→部位 P&L)、`models/baseline.py`。目前研究流程不依賴它們。

---

## 5. 外部相依

- **LLM 服務**:本地 vLLM(`scripts/serve_local.sh`,Qwen3-Coder-30B-A3B-Instruct-FP8)或任何 LiteLLM 支援的雲端模型。
- **期權資料**:ThetaData 本地終端(免費,port 25503)/ Databento OPRA(付費,成本守門);underlying 用 yfinance。
- **永續資料**:Binance USDⓈ-M 公開 REST(`fapi.binance.com`),免 API key、不下單。
- **打包**:uv / hatchling;測試 pytest(目前 69 passed)。
