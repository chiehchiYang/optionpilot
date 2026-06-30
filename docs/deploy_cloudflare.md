# 用 Cloudflare 把 OptionPilot 網頁 UI 安全公開(WhatsApp 打 /op 給連結)

**目標**:WhatsApp 打 `/op` → 拿到一個連結 → 手機瀏覽器開啟 → 就是本機那個 Gradio UI(圖表 / 串流 /
雙研究台)。徹底避開「Hermes 會跳出來」「圖片跑不出來」—— 因為互動在瀏覽器裡,不靠 Hermes 每則的 LLM
路由,圖表也由瀏覽器原生渲染。

```
WhatsApp 打 /op ─▶ Hermes 回連結 https://optionpilot.cc-sherry.org
                                    │ Cloudflare Tunnel + Access(登入保護)
你按連結 ─▶ 手機瀏覽器 ─▶ 本機的 optionpilot-ui(Gradio :7860,圖表/串流/雙台)
```

**前提**:① UI 跑在哪台(建議 **Linux GPU 機**,模型也在那;Mac 亦可)。② 一個**託管在 Cloudflare 的
網域**。這條路**不需要 MCP server**(MCP 是「在 WhatsApp 裡直接對話」那條;給連結這條更單純)。

---

## 1. 跑 UI(常駐)
```bash
uv run optionpilot-ui            # Gradio 監聽 0.0.0.0:7860
# 常駐建議:tmux / nohup,或包成 systemd service
```
(Mac 若遇到 `gradio has no attribute 'Blocks'` 的安裝問題,見 [deploy_mac.md](deploy_mac.md)。)

## 2. Cloudflare Tunnel(綁你的網域)
```bash
brew install cloudflared          # 或下載官方 binary
cloudflared tunnel login
cloudflared tunnel create optionpilot          # 產生 tunnel + 憑證 json
cloudflared tunnel route dns optionpilot optionpilot.cc-sherry.org
```
`~/.cloudflared/config.yml`:
```yaml
tunnel: <TUNNEL-ID>
credentials-file: /home/<you>/.cloudflared/<TUNNEL-ID>.json
ingress:
  - hostname: optionpilot.cc-sherry.org      # 只綁這一個 hostname
    service: http://localhost:7860
  - service: http_status:404           # 其他一律 404,不曝露機器其他東西
```
```bash
cloudflared tunnel run optionpilot     # 或 cloudflared service install 設成開機常駐
```

## 3. 🔴 登入保護(**必做**)— Cloudflare Access
**Gradio 本身沒有任何登入**。沒有 Access,任何拿到連結的人都能用你的 LLM、看你的研究、甚至花
Databento 的錢。設定:

> Cloudflare **Zero Trust → Access → Applications → Add → Self-hosted**
> - Application domain: `optionpilot.cc-sherry.org`
> - Policy:**Allow**,Include → **Emails** = 你的 email(登入用 Email OTP 或 Google)

之後你在手機按連結時,會先過一次 Cloudflare 登入(cookie 記住,之後免再登)。

**(可選)第二道鎖 — Gradio 內建 basic auth**(縱深防禦):
```bash
# .env
OPTIONPILOT_UI_AUTH=帳號:密碼
```
設了之後,UI 啟動就會要求帳密(在 Cloudflare Access 之外再加一層);留空則只靠 Access。

## 4. `/op` 回連結的 skill(超簡單)
這條路的 `/op` 不呼叫任何工具,只回固定連結。Hermes 的 `op` skill:
```markdown
---
name: op
description: 回傳 OptionPilot 網頁 UI 的連結。
command: op
---
回覆這一行(不要做別的):「OptionPilot:https://optionpilot.cc-sherry.org —— 點開直接用(圖表/雙台都在)。」
```
(你甚至可以把網址加書籤,連 `/op` 都省了。)

---

## 5. 安全檢查清單
- **Cloudflare Access 一定要設** —— Gradio 無內建登入,這是唯一的門。
- ⚠️ **GUI 會 auto-approve 付費抓取**(跟 MCP 的「只用免費」不同)。因為只開放給你,可接受;想更保險就在
  `.env` 設 `OPTIONPILOT_MAX_FETCH_USD`(每次抓取成本上限)守門。
- **ingress 只綁 `:7860` 那個 hostname**,別把機器其他服務露出去(cloudflared 本身不開 inbound port)。
- 保護好:**tunnel 憑證 json**、機器的 **`.env`**(LLM/Databento key)、Access 的設定。
- **UI 要一直開著**(+ tunnel 常駐),否則連結打不開。
- 只用 **HTTPS**(Cloudflare 自動給 TLS),不要裸 HTTP。

## 6. 快速臨時版(免網域,測試用)
只想先試一下、還沒設網域 + Access:
```bash
cloudflared tunnel --url http://localhost:7860     # 給一個臨時 trycloudflare.com 網址
```
⚠️ 但這個**沒有登入保護**,只靠網址隨機性,別長期或放真 key 在上面跑 —— 正式用一定要走 §2+§3。
