# OptionPilot — 計畫（v3，2026-06-21 更新）

## 目標與願景

**一句話**：一個**自主的期權策略研究 agent**——像 ml-intern 是「會自己跑實驗的 ML 工程師」，
OptionPilot 是「**會自己研究期權策略、並用一整套嚴謹回測去檢驗它到底能不能賺錢的研究員**」。

由兩個支柱組成：

**支柱一：像 ml-intern 的「自主研究迴圈」** — 給一個自然語言任務（例：「研究賣價差策略在 SPY 上的表現」），
它自己跑完整實驗迴圈，不用你下每一步：

```
提出假設 → 抓資料 → 工程特徵 → 建模型/策略 → 回測 → 讀指標
   → 提出下一個該試的改進 → 再回測 → 比較 → 記錄
   → (迭代收斂) → 產出：最佳策略 + 完整實驗紀錄 + 誠實結論
```

它會自己提假設、自己迭代、自己記錄每次實驗（`ExperimentLoop` + `Planner` + `ExperimentTracker`）。

**支柱二：一整套「可檢驗」的回測系統** — 跟「相信我的 AI 訊號」產品最大的差別：每個策略都要通過同一套
嚴格、誠實的檢驗才算數：

- **Out-of-sample / walk-forward**：規則只在沒看過的資料上評估，杜絕過擬合
- **真實成本**：期權買賣價差、滑價、手續費、行權/指派全算進去
- **完整指標**：Sharpe、最大回撤、勝率、turnover + 最壞情境（黑天鵝）壓力測試
- **可重現、可比較**：每次 run 的設定+結果記進 DuckDB，不同策略/變體 head-to-head 對比
- **誠實面對負面結果**：策略沒用就報告它沒用——這才是研究員，不是業配

**成功的定義**：不是「找到魔法賺錢訊號」（不切實際），而是——
> 能用這套系統，對任何候選策略快速給出「**扣掉成本、在沒看過的資料上，它到底還剩多少 edge、最壞會賠多少**」
> 的誠實答案，讓你只把真金白銀放在通過檢驗的策略上。

## 0. 重大調整（相對 v2）

- **目標確定為「真的拿來交易賺錢」** → 方法論優先，拒絕過擬合表演。
- **Nudge 機制已移除**。原本的「後處理規則加權」理論站不住、且對真金白銀目標是過擬合風險。
- **策略核心已鎖定（2026-06-21，依研究）**：**定義風險的指數/ETF 賣方策略**
  （cash-secured 指數 put、covered call、put credit spread / iron condor）。
  避開：裸賣 strangle/put、反向/槓桿 VIX ETP、單一個股賣方。詳見 [docs/strategy_research.md](docs/strategy_research.md)。
- **誠實預期**：研究顯示賣方 alpha 近 ~15 年已大幅縮水（Chicago Fed 2025）；合理定位是
  「回撤較小的類 beta 股票替代品」，**非穩定 alpha**。OptionPilot 的價值在於**誠實量化** edge 還剩多少。
- 不可妥協的驗證原則：**out-of-sample / walk-forward + 真實成本（價差/滑價/手續費）+ 壓力測試
  （Feb2018 / Mar2020 / 2022）**，碰真錢前先 paper trading + 小額 + 風控。

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
- 策略核心已定（定義風險賣方），這些現在依該策略設計（見「下一步」）。

## 3. 技術選擇（仍有效）

| 層級 | 技術 |
|---|---|
| 資料層 | Databento（OPRA 歷史）+ Parquet + DuckDB；yfinance（標的價） |
| Greeks | 自寫 Black-Scholes / IV |
| Agent 層 | 自寫 Experiment Loop + LiteLLM（多模型）+ ContextManager + ToolRouter + DoomLoop |
| 本地 LLM | vLLM + Qwen3-Coder-30B FP8（driver 570 / cu128，見 scripts/） |
| 介面 | Typer（CLI）→ Streamlit（可選） |
| 實驗追蹤 / 測試 | DuckDB + Parquet；pytest |

## 4. 下一步（策略核心已定）

1. 設計賣方策略的回測：`BacktestEngine.run` 算**賣 put / credit spread 的損益**（權利金收入、到期/行權、
   **真實成本：價差+滑價+手續費**），不是股票代理。
2. `calculate_features`：賣方策略需要的特徵（IV rank、VRP proxy、delta/到期選擇規則）。
3. **walk-forward 切分** + **壓力測試**（Feb2018 / Mar2020 / 2022）。
4. 用本地 Qwen 端到端跑出**誠實的** out-of-sample 數字（含最壞情境）。
5. paper trading 驗證 → 小額實盤 + 風控，再談放大。

## 5. 差異化一句話

> 別人給你「相信我的 AI 訊號」；
> **OptionPilot 是一個會自己跑實驗、用 out-of-sample 回測與真實成本誠實驗證策略到底能不能存活的期權研究 intern。**
