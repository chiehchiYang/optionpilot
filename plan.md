# OptionPilot — 計畫（v3，2026-06-21 更新）

> 自主的期權策略研究 Agent：像一個「期權研究 intern」，自己跑完整的
> 資料 → 特徵 → 模型 → 回測 → 報告 實驗迴圈，並用**嚴謹、誠實**的回測驗證每個訊號。

## 0. 重大調整（相對 v2）

- **目標確定為「真的拿來交易賺錢」** → 方法論優先，拒絕過擬合表演。
- **Nudge 機制已移除**。原本的「後處理規則加權」理論站不住、且對真金白銀目標是過擬合風險。
- **策略核心改為「先研究再定」**：正用 deep-research 調查散戶（$50k–$250k、中等風險、美股）
  實際有實證 edge 的期權策略（波動率風險溢酬／賣方策略等）。報告出來再定策略核心。
- 不可妥協的驗證原則：**out-of-sample / walk-forward + 真實成本（價差/滑價/手續費）**，
  碰真錢前先 paper trading + 小額 + 風控。

## 1. 已完成（可運作、有測試）

- **Agent harness**（借 ml-intern 模式，全新寫、零 HF 耦合）：`ExperimentLoop`（agentic 迴圈）、
  `ContextManager`（壓縮）、`ToolRouter`（+ approval gating）、`DoomLoopDetector`、多模型 `LLMClient`(LiteLLM)。
- **資料層**：`DatabentoFetcher`（OPRA 歷史，**抓取前成本 guard** 保護 $125 credit，Parquet 快取，mock 測試）。
- **回測指標**：Sharpe / MaxDD / WinRate / summarize。
- **Greeks**：本地 Black-Scholes / IV（Databento 不給 greeks）。
- **本地模型（零成本開發）**：vLLM 在 RTX Pro 6000 上服務 Qwen3-Coder-30B-A3B FP8；
  agent 端到端 tool-calling 已驗證（見 `scripts/setup_vllm.sh` / `serve_local.sh`）。

## 2. 尚未實作（待策略核心定案後接上）

- `calculate_features`、`BaselineModel`、`BacktestEngine.run`、`ExperimentTracker`、`generate_report` 仍是 stub。
- 這些的具體設計**等 deep-research 定出策略核心**再做，避免做白工。

## 3. 技術選擇（仍有效）

| 層級 | 技術 |
|---|---|
| 資料層 | Databento（OPRA 歷史）+ Parquet + DuckDB；yfinance（標的價） |
| Greeks | 自寫 Black-Scholes / IV |
| Agent 層 | 自寫 Experiment Loop + LiteLLM（多模型）+ ContextManager + ToolRouter + DoomLoop |
| 本地 LLM | vLLM + Qwen3-Coder-30B FP8（driver 570 / cu128，見 scripts/） |
| 介面 | Typer（CLI）→ Streamlit（可選） |
| 實驗追蹤 / 測試 | DuckDB + Parquet；pytest |

## 4. 下一步

1. **等 deep-research 報告** → 與你一起選定 1–3 個有實證、可控風險的策略核心。
2. 依選定策略，實作 `calculate_features` → `BacktestEngine.run`（**含真實成本 + walk-forward 切分**）→ 指標。
3. 用本地 Qwen 端到端跑出**誠實的** out-of-sample 回測數字。
4. paper trading 驗證 → 小額實盤 + 風控，再談放大。

## 5. 差異化一句話

> 別人給你「相信我的 AI 訊號」；
> **OptionPilot 是一個會自己跑實驗、用 out-of-sample 回測與真實成本誠實驗證策略到底能不能存活的期權研究 intern。**
