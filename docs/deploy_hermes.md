# 透過 Hermes Agent 用 WhatsApp 操作 OptionPilot

[Hermes Agent](https://github.com/NousResearch/hermes-agent)(Nous Research)是自架的 AI agent
框架,內建 **Messaging Gateway**(WhatsApp / Telegram / Signal…),把訊息收發、session、白名單、
語音都做好了。我們讓 **Hermes 當溝通層,OptionPilot 透過 MCP 當研究專家**:

```
你 ⇄ WhatsApp ⇄ Hermes(對話大腦 + 通訊閘) ──MCP──▶ optionpilot-mcp
                                                    └▶ build_loop(desk).run(訊息)
                                                       (完整 playbook + 回測 + trajectory + 記憶)
```

OptionPilot 的嚴謹研究流程整套跑在 `optionpilot_chat` 工具**裡面**,所以不是把一堆零散工具丟給
Hermes 的 LLM 亂編排、丟失紀律。

---

## 1. 前置

- **OptionPilot 裝好,且自己有一個 LLM 後端**(`.env` 的 `OPTIONPILOT_MODEL` … —— 本地 Ollama /
  雲端 / OpenCode Zen 皆可)。Hermes 也有它自己的模型;兩個 LLM 各司其職。
- 裝 MCP 額外相依:
  ```bash
  uv sync --extra data --extra mcp        # 或 pip install -e ".[data,mcp]"
  ```
- **Hermes 裝好,並完成 WhatsApp 設定**(它的 Meta/Baileys 接法見 Hermes 官方文件)。建議用一隻
  **專屬門號**當 bot(WhatsApp Business API 號碼會被佔用,不能同時用在一般 app)。

## 2. MCP server 怎麼跑

是 **stdio**:你**不用**自己常駐它 —— **Hermes 會幫你啟動**(把它當子行程,用 stdin/stdout 溝通)。
要手動測試可跑 `uv run optionpilot-mcp`(會等 stdio 輸入,Ctrl-C 結束)。
它提供兩個工具,Hermes 加前綴後是 **`mcp_optionpilot_chat`** 與 **`mcp_optionpilot_reset`**。
**只用免費資料源** —— 付費 Databento 一律自動拒絕,WhatsApp 那端永遠不會花到錢。

**回覆模式(對齊 GUI)**:`chat` 回的內容跟 Gradio GUI 一樣 —— **工具活動軌跡(🔧 …)+ `---` +
最終結論 + 該輪產生的圖表**。兩個環境變數可調(預設都開):
- `OPTIONPILOT_MCP_SHOW_STEPS=0` 關掉步驟軌跡(只回結論,適合手機嫌吵時)
- `OPTIONPILOT_MCP_RETURN_IMAGES=0` 關掉圖表

> ⚠️ 兩個與 GUI 的差異:① **不是即時串流** —— 一次 MCP 呼叫只回一次,軌跡會跟結論「最後一起到」
> (要逐步即時,靠 `/op` skill 先回「研究中…」)。② **圖表要 Hermes 幫忙轉**:我們已把圖以 MCP
> image content 回出去,但**最終能不能在 WhatsApp 顯示,取決於 Hermes 是否把 MCP 圖片轉成媒體訊息
> 送出**(它會送語音/GIF,圖片應該也行,但請實測)。轉不出來就退回純文字,不會壞。

## 3. 把它接到 Hermes(`~/.hermes/config.yaml`)

Hermes 的 MCP server 設定在 `~/.hermes/config.yaml` 的 `mcp_servers` 區段。加上:
```yaml
mcp_servers:
  optionpilot:
    command: "uv"
    args: ["run", "--directory", "/path/to/optionpilot", "optionpilot-mcp"]
    # tools:                       # (可選)只露出我們的兩個工具
    #   include: [chat, reset]
```
用 `uv run --directory <專案路徑>` 讓它在 OptionPilot 專案目錄裡跑,這樣它會讀到該目錄的 **`.env`**
(OptionPilot 自己的 LLM 後端 key 從這裡來)。

> ⚠️ **環境變數**:Hermes 對 stdio server **不會**自動把你 shell 的環境全帶進去,只帶 `env:` 裡明寫
> 的。但沒關係 —— OptionPilot 是用專案目錄的 **`.env`** 載入設定(`Config.load()` 會讀 `.env`),
> 所以 `OPTIONPILOT_MODEL` / 各家 key 放 `.env` 即可,不必寫進 Hermes config。

載入(active session 中)或重啟:
```bash
/reload-mcp          # 在 hermes 對話中重載 MCP
# 或重開:hermes chat
```
Hermes 啟動時會自動探索並註冊工具,名稱就是 **`mcp_optionpilot_chat`** / **`mcp_optionpilot_reset`**。

## 4. 讓訊息進到 OptionPilot — 兩種做法

### 4a.(最穩)讓專屬號碼**預設就是 OptionPilot**(沒有「模式」可跳出)
你既然用一隻專屬門號,最不會「跳出來」的做法是:**把那支號碼的 Hermes persona/系統指令設成永遠轉發**
—— OptionPilot 變成基線行為,不是會被 LLM 遺忘的暫時狀態。persona 系統指令(依 Hermes 的 persona/
system-prompt 設定方式放入):

```
你是一個轉發到 OptionPilot 研究台的閘道。對使用者的【每一則】訊息,你【唯一】的動作就是呼叫
mcp_optionpilot_chat(conversation_id=本聊天固定id;desk:含永續/合約/funding/網格→"crypto",
否則→"options"),並把回覆原樣轉述。不論訊息內容是什麼,都【絕不】用你自己的知識回答、【絕不】跳過
工具。只有當使用者送出【正好】是「/general」時,才臨時切回一般 Hermes 回答一則,然後恢復轉發。
```

### 4b.(更可靠的 `/op`)一次性指令,**非黏著模式**
比「進入模式」更不會跳的做法:**每則訊息都用 `/op <訊息>` 呼叫**。`/op` 是 slash 指令、由 Hermes
**確定性派發**,每則都是明確的一次性呼叫 —— **沒有「模式」要記,就沒有東西會跳回去**。代價只是每則
多打 `/op`。沒加 `/op` 的訊息照走一般 Hermes,同一支號碼兩用。

```markdown
---
name: op
description: 把這則訊息交給 OptionPilot 研究台(一次性,非黏著模式)。
command: op
---

# OptionPilot(一次性指令)

每當使用者以 `/op <訊息>` 呼叫時,你【唯一】的動作 = 呼叫 `mcp_optionpilot_chat`(
  message=`<訊息>`、conversation_id=【本聊天的固定 id】、desk 見下),把回覆原樣轉述。

- **絕不**用你自己的知識回答、**絕不**跳過工具、**絕不**自行總結。
- desk:`<訊息>` 含永續/合約/funding/網格(或 `/perp`)→ `desk="crypto"`;否則(或 `/options`)→
  `desk="options"`。
- **conversation_id 在同一個聊天裡每次都用同一個固定值** —— 這樣 OptionPilot 的研究 session 才會
  延續、多輪上下文不斷。
- 這是一次性指令,**不要進入或維持任何模式**;研究較久時可先回「研究中…」,工具回來再給結果。
```

> **可靠度排序**:一次性 `/op`(本節,最不會跳,但每則要打 `/op`)≈ 單一用途 profile(§4a,零打字但
> 仍是 profile 的 LLM 在決定)> 黏著式 `/op` 模式(最會跳,已不建議)。三者都**留在 MCP**,所以自然
> 語言、Hermes 功能、圖表全保留。唯一 100% 確定性的是「把 LLM 從路由拿掉」:直接 WhatsApp webhook,
> 或硬鎖 model-switch(需 `/v1` shim、失去自然離開與 Hermes 功能)—— 兩者都比較重,非必要不做。

## 5. 跟 Cloudflare / WhatsApp 的關係

- WhatsApp 的收發、webhook、白名單都由 **Hermes** 處理(見 Hermes 文件)。
- 若 Hermes 的 WhatsApp 走 Meta 官方需要對外 webhook,用 **Cloudflare Tunnel** 把它安全公開
  (見 [deploy_cloudflare.md](deploy_cloudflare.md),若已建立)。
- OptionPilot 的 MCP server 只跟**本機的 Hermes**用 stdio 溝通,不對外曝露。

## 6. 注意

- **白名單**:在 Hermes 端把允許的號碼設好(`WHATSAPP_ALLOWED_USERS`),避免陌生人觸發研究。
- **慢任務**:一次真回測要跑數分鐘;Hermes 端先回「研究中…」,工具同步回來再轉述。
- **資料**:預設只用免費來源(yfinance / Binance / VIX)。選擇權真實 chain 需要 ThetaData 終端在
  本機跑著;否則永續台 / 選股 / 基本面 / VIX 都零設定可用。
