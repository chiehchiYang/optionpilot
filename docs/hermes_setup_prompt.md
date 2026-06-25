# 讓 Hermes 自己接上 OptionPilot(可直接貼給 Hermes 的指令)

把下面「--- 貼給 Hermes ---」之間的整段,當成一個任務貼給 Hermes。
**先把 `<OPTIONPILOT_DIR>` 換成你這台機器上的 OptionPilot 專案路徑**(例如這台是
`/media/user/data2/chiehchi/project`)。完整背景見 [deploy_hermes.md](deploy_hermes.md)。

前提:OptionPilot 已 `uv sync --extra data --extra mcp`,且專案目錄有 `.env`(它自己的 LLM key)。

---- 貼給 Hermes ----

請幫我把一個本地 MCP server「OptionPilot」(選擇權/永續/選股研究)接進來,並建立一個 `/op` 模式。
OptionPilot 專案路徑是 `<OPTIONPILOT_DIR>`。請依序執行:

**1. 註冊 MCP server** — 編輯 `~/.hermes/config.yaml`,在 `mcp_servers` 下加入(沒有該區段就新增):
```yaml
mcp_servers:
  optionpilot:
    command: "uv"
    args: ["run", "--directory", "<OPTIONPILOT_DIR>", "optionpilot-mcp"]
```
(它是 stdio server,你會自己把它當子行程啟動;它用該目錄的 `.env` 載入自己的 LLM 後端,不需要我
給你 key。它只用免費資料源,不會花錢。)

**2. 重載並確認** — 執行 `/reload-mcp`,然後列出 MCP 工具,確認有 **`mcp_optionpilot_chat`** 和
**`mcp_optionpilot_reset`** 兩個。若沒出現,檢查 `<OPTIONPILOT_DIR>` 是否正確、`uv` 是否在 PATH。

**3. 建立 `/op` skill** — 新增一個名為 `op` 的 skill,指令內容如下:

> # OptionPilot 模式
> 當使用者輸入 `/op`(可帶第一個問題)時,進入「OptionPilot 研究模式」:
> 1. 回一句確認:「已進入 OptionPilot 研究模式(選擇權台)。直接問選擇權/永續/選股/基本面;說
>    「結束」或 `/end` 離開。」
> 2. 在此模式中,對使用者的每一則訊息都呼叫 **`mcp_optionpilot_chat`**(conversation_id 用這個聊天
>    的固定 id),把回覆原樣轉述,結尾加上:`（OptionPilot 模式 — 說「結束」離開）`。不要用自己的
>    知識回答市場問題。
> 3. desk 切換:訊息是 `/perp` 或提到永續/合約/funding/網格 → 帶 `desk="crypto"`;`/options` 或選
>    擇權/個股 → `desk="options"`。
> 4. 離開:使用者說「結束」/「exit」/「quit」或輸入 `/end` → 回「已離開 OptionPilot 模式。」並恢復
>    正常行為,不再自動呼叫該工具。
> 5. 研究較久時先回「研究中…」,工具回來再給完整結果。

**4. 驗證** — 進入 `/op`,問「分析 NOKUSDT 的資金費率」,你應該會呼叫 `mcp_optionpilot_chat`
(`desk="crypto"`)並回研究結果;接著我說「結束」,你應離開模式。完成後跟我回報結果。

---- 貼給 Hermes 結束 ----

## 給你(人類)的小抄
- 接好後日常用法:WhatsApp 傳 `/op` → 進入模式 → 直接問 → 說「結束」離開。
- 若 Hermes 偶爾跳出模式(軟鎖),用 `/end` 當硬後門;真的常跳再回報,我們升級成 model-switch 硬鎖。
- 白名單(只允許你的號碼)在 Hermes 端設(`WHATSAPP_ALLOWED_USERS`)。
