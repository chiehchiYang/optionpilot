# OptionPilot — 實作計畫（定案版 v2）

> 自主的期權策略研究 Agent：像一個「期權策略研究 intern」，自己跑完整的
> 資料 → 特徵 → 模型(含 Nudge) → 回測 → ablation → 報告 實驗迴圈，並用嚴謹回測證明每個訊號。

---

## 0. 已定案的核心決定

| 項目 | 決定 | 理由 |
|---|---|---|
| **專案名稱** | **OptionPilot** | 與 NudgeVAD 無關 |
| **Repo** | `/media/user/data2/chiehchi/project`（已 `git init`，branch `main`，獨立於上層自駕 repo） | 不混入自駕專案 |
| **回測資料** | **Databento OPRA**（歷史 pay-as-you-go $0.04/GB，新帳號 $125 免費 credit，資料回到 2013） | 真期權回測、$125 起步免花錢 |
| **Greeks / IV** | **自己算**（內建 Black-Scholes 模組） | Databento 不提供預算 greeks |
| **即時報價** | **先不碰**（Databento live 已改 $199/月）；要時用 yfinance 延遲報價代打 | 回測只吃歷史，不付月費 |
| **Nudge 機制** | **後處理規則加權層**：`p_final = clip(p_model ⊕ Σ ruleᵢ(indicators)·wᵢ, 0, 1)` | 可插拔 → 天然支援 ablation |
| **Agent harness** | **全新寫，借 ml-intern 的模式**（不 fork、零 HF 耦合） | 乾淨、可控 |
| **訊號靈感** | 借 Stockwe 的**期權 flow 訊號**（異常期權活動、put/call ratio、premium flow）當特徵/nudge 規則 | 用回測證明它們有沒有用 |
| **成本控制** | 資料層內建**抓取前大小/費用估算 guard**；昂貴抓取走 approval gating | 保護 $125 credit |
| **MVP 標的** | **SPY**（流動性最好、易對照） | 可再換 NVDA 等 |

**Out of scope（寫進未來擴充，MVP 不做）**：暗池 / 機構資金流（需付費 prints）、社群情緒。
**可選便宜加分項**：SEC EDGAR Form 4 內部人交易（免費）。

---

## 1. 整體架構（借 ml-intern 模式，特化成期權研究）

```
使用者輸入（CLI / 自然語言）
        ↓
   CLI（interactive / headless --auto-approve）        ← 借 ml-intern 三種模式
        ↓
   Agent Core = Experiment Loop                        ← 借 ml-intern agentic loop
     • litellm 呼叫（Claude / DeepSeek / Grok / 本地）
     • ContextManager（長對話自動壓縮）
     • Approval Gating（昂貴/破壞性操作要批准）
     • Doom-Loop Detector（防鬼打牆）
     • Planner（提出下一個該試的實驗，非亂調參）
        ↓
   ToolRouter（統一管理工具 + ToolSpec）
        ↓
   Tools Layer（期權研究工具）
     • fetch_options_data     （Databento OPRA + Parquet 快取 + 成本 guard）
     • calculate_features     （技術指標 + 期權 flow 訊號 + 自算 greeks/IV）
     • predict_buy_point      （模型輸出 → NudgeLayer 後處理）
     • run_backtest           （Sharpe / MaxDD / WinRate / turnover）
     • generate_report        （策略 + ablation 表 + 敘述）
        ↓
   ExperimentTracker（DuckDB/Parquet 記錄每次 run 的 config+指標，可比較）
        ↓
   輸出（買點建議 + 回測指標 + ablation 報告）
```

---

## 2. 技術選擇

| 層級 | 技術 |
|---|---|
| 資料層 | Databento（OPRA 歷史）+ Parquet 快取 + **DuckDB** 查詢；yfinance（標的價/延遲報價） |
| 模型層 | XGBoost（baseline）→ PyTorch Transformer；**NudgeLayer**（後處理規則加權） |
| Greeks | 自寫 Black-Scholes / IV solver |
| Agent 層 | 自寫 Experiment Loop + **LiteLLM**（多模型）+ ContextManager + ToolRouter + DoomLoop |
| 介面層 | **Typer**（CLI）→ Streamlit（可選 Dashboard） |
| 實驗追蹤 | **DuckDB + Parquet**（run config + 指標）；可選上傳 HF dataset |
| 測試 | pytest |

---

## 3. Roadmap

### Phase 1 — 垂直切片 MVP（先證明整條 pipeline 通）
目標：**單一標的 SPY**，用 $125 免費 credit，跑通「資料 → 特徵 → baseline+nudge → 回測 → 報告」。
- [ ] 資料層：`DatabentoFetcher`（OPRA 歷史）+ Parquet 快取 + **抓取前成本估算 guard**
- [ ] `calculate_features`：基本技術指標 + 自算 greeks/IV + 1~2 個期權 flow 訊號（put/call ratio、爆量）
- [ ] Baseline 模型（XGBoost）+ **NudgeLayer**（先 1~2 條規則，如 RSI<30 上調買進機率）
- [ ] 回測引擎：輸出 Sharpe / MaxDD / WinRate / turnover
- [ ] **Ablation：有 nudge vs 沒 nudge** 的回測對比表
- [ ] ToolSpec + ToolRouter；Experiment Loop（**Phase 1 先 human-in-loop：每輪回測停下給結果+下一步建議，批准才續**）
- [ ] LiteLLM 整合（先接 DeepSeek）
- [ ] CLI：`optionpilot "分析 SPY 的買點策略"`（interactive + headless）
- [ ] 第一版 README

### Phase 2 — 功能強化
- [ ] Transformer 模型
- [ ] 完善 NudgeLayer + 正式 Ablation Study 框架
- [ ] ExperimentTracker（DuckDB）+ Planner（自動提出下一個實驗）
- [ ] **全自動模式**（intern 自己迭代到達標/用完預算）+ guardrail
- [ ] 更多期權 flow 訊號（premium flow、分鐘級多空量）；可選 SEC Form 4
- [ ] Streamlit Dashboard（買點 + 回測圖 + ablation）
- [ ] 2~3 檔標的完整測試

### Phase 3 — 打磨與展示
- [ ] README 美化（架構圖、demo GIF）、錯誤處理、日誌、配置檔
- [ ] Demo 講稿（重點：intern 的實驗思路 + nudge ablation 的量化提升）

---

## 4. 立即第一步（建議順序）
1. **建 repo 骨架**：目錄結構、`.gitignore`、`pyproject.toml`、`.env.example`（Databento key）
2. **資料層 `DatabentoFetcher`**（含成本 guard + Parquet 快取）— 最危險的地基，先打穩
3. **ToolSpec + ToolRouter**
4. **Experiment Loop + LiteLLM**（接 DeepSeek、human-in-loop）
5. **Baseline + NudgeLayer + 回測引擎 + ablation**
6. **CLI 入口**

---

## 5. 差異化一句話
> 別人（Stockwe）給你「相信我的 AI」的訊號儀表板；
> **OptionPilot 是一個會自己跑實驗、用嚴謹回測證明每個訊號、並量化 nudge 帶來多少 Sharpe 提升的期權研究 intern。**
