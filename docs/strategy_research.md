# 策略研究決策記錄（2026-06-21）

> 來源：deep-research 工作流（6 角度、25 來源、115 claims、對抗式查證後 23 confirmed / 2 killed）。
> 問題：$50k–$250k 散戶、中等風險、美股期權——哪些策略**有實證、扣成本後真的還賺得到**？

## 結論（一句話）

「賣方收溢酬」這條路**學理真實、反覆驗證**，但近 ~15 年那個「免費 edge」**很可能已被競爭掉**。
合理定位是「**回撤比買進持有小的、類 beta 的股票替代品**」，**不是穩定 alpha 印鈔機**。

## 證據三層

1. **edge 存在（高信心）**：波動率風險溢酬（VRP）——指數隱含波動率系統性 > 實際波動率，賣方被付錢。
   Bakshi-Kapadia(2003)、Carr-Wu(2009)、Bollerslev(2009)。**僅在指數（SPX）成立；個股 VRP 不顯著。**
2. **歷史回測漂亮但有但書**：CBOE PUT / BXM 指數 1986–2018 Sharpe 高於 S&P500、回撤更小（PUT -35% vs S&P -51%）。
   ⚠️ 但：CBOE 自家利益相關白皮書、資料只到 2018（沒涵蓋 2020/2022）、Sharpe 嚴重低估負偏態肥尾。
3. **edge 正在消失（最新、最傷）**：Chicago Fed WP 2025-17（Dew-Becker & Giglio）——過去 10–15 年期權 alpha
   已基本降到零，結構轉折 ~2010–12，剩餘溢酬「不超過 CAPM beta 該給的」。
   （單一未正式發表工作論文；「全沒了」的最強框架在查證時被部分否決 → 結論是「alpha 大幅縮水」非「鐵定歸零」。）

## 決策：策略核心

**鎖定為「定義風險的指數/ETF 賣方策略」**：

| ✅ 採用 | ❌ 避開 |
|---|---|
| Cash-secured 指數/ETF put（PUT 指數做法） | 裸賣 strangle/put（無限尾部風險） |
| Covered call（BXM 做法） | 反向/槓桿 VIX ETP（Volmageddon 一天 -90%） |
| Put credit spread / iron condor（封住尾部） | 單一個股賣方（VRP 不顯著） |

理由：$50k–$250k + 中等風險適合定義風險結構、券商權限要求低；散戶資料顯示單邊買方系統性虧錢，
賺錢的是賣方，但資料中賺錢的賣方多為**裸賣**（正是要避開的）→ 走**定義風險**賣方。

## 對 OptionPilot 的意義

這結論反而證明專案價值：OptionPilot 要做的正是「對任何策略給出『扣成本、out-of-sample 後還剩多少 edge、
最壞賠多少』的誠實答案」。回測系統因此要：

1. 用 **2019 年後**（涵蓋 2020/2022）資料 + **扣真實成本**回測上述賣方策略
2. 對 **Feb 2018 / Mar 2020 / 2022** 做壓力測試
3. 誠實量化：在使用者成本結構下還剩多少、最壞情境多深

## 主要來源

- [Carr-Wu 2009 (RFS)](https://engineering.nyu.edu/sites/default/files/2019-01/CarrReviewofFinStudiesMarch2009-a.pdf) — VRP
- [Bakshi-Kapadia 2003](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=267106) — 負波動率風險溢酬
- [Bollerslev-Tauchen-Zhou (Fed 2007)](https://www.federalreserve.gov/pubs/feds/2007/200711/200711pap.pdf) — VRP 預測力
- [CBOE/Wilshire 2019 benchmark study](https://cdn.cboe.com/resources/spx/wilshire-options-based-benchmark-indexes-2019.pdf) — PUT/BXM 績效（注意利益相關 + 只到 2018）
- [Chicago Fed WP 2025-17](https://www.chicagofed.org/-/media/publications/working-papers/2025/wp2025-17.pdf) — alpha 已縮水
- [Volmageddon, FAJ 2021](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3819342) — 短波動產品崩潰機制
- [An Anatomy of Retail Option Trading](https://www.brettonwoodsskiconference.com/uploads/b/f9bfc8b0-0251-11ed-a646-3dea17112d2f/An%20Anatomy%20of%20Retail%20Option%20Trading.pdf) — 散戶基準率

## 待辦/開放問題

- 2024–2026 specific net-of-cost Sharpe 幾乎沒有直接證據（多為歷史或推論）。
- 真實滑價建模細節、1256 稅務處理 → 實作回測時補。
