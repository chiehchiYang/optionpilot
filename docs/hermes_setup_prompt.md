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

**3. 建立 `/op` skill(一次性,非黏著模式)** — 新增一個名為 `op` 的 skill,指令內容如下。
重點:**它是「一次性」的 —— 每則訊息都用 `/op <訊息>` 呼叫,不進入也不維持任何模式**(這樣就沒有
「模式」可以被忘記、不會跳回去):

> # OptionPilot(一次性指令)
> 每當使用者以 `/op <訊息>` 呼叫時,你【唯一】的動作 = 呼叫 **`mcp_optionpilot_chat`**(
>   message=`<訊息>`、conversation_id=【本聊天的固定 id】、desk 見下),把回覆原樣轉述。
> - **絕不**用自己的知識回答、**絕不**跳過工具、**絕不**自行總結。
> - desk:`<訊息>` 含永續/合約/funding/網格(或 `/perp`)→ `desk="crypto"`;否則(或 `/options`)
>   → `desk="options"`。
> - **conversation_id 必須在同一個聊天裡每次都用同一個固定值** —— 這樣 OptionPilot 的研究 session
>   才會延續、多輪上下文不斷。
> - 這是一次性指令,**不要進入或維持任何模式**;研究較久時可先回「研究中…」,工具回來再給結果。

**4. 驗證** — 傳 `/op 分析 NOKUSDT 的資金費率`,你應呼叫 `mcp_optionpilot_chat`(`desk="crypto"`)
並回研究結果;再傳 `/op 那它適合做網格嗎`,應沿用**同一個 conversation_id**(記得上一輪)。回報結果。

---- 貼給 Hermes 結束 ----

## 給你(人類)的小抄
- 日常用法:WhatsApp **每則前面加 `/op`**(例:`/op BTDR 近期基本面`)。沒加 `/op` 的訊息就走一般
  Hermes —— 所以同一支號碼兩用、互不干擾。
- **為什麼這樣最不會跳**:`/op` 是 slash 指令、由 Hermes 確定性派發,每則都是明確的一次性呼叫,
  **沒有「模式」要記、就沒有東西會跳回去**。多打四個字,換近乎確定性。
- 多輪記憶靠 skill 帶**固定 conversation_id**(已寫在指令裡);所以分開的 `/op` 之間仍記得前文。
- 想「零打字、整支號碼全自動進 OptionPilot」→ 改用**單一用途 profile**(見 deploy_hermes.md §4a)。
- 白名單(只允許你的號碼)在 Hermes 端設(`WHATSAPP_ALLOWED_USERS`)。
