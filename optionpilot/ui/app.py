"""Gradio chat UI for OptionPilot — two ISOLATED desks as tabs.

Tab「股票期權」runs the options-research intern; tab「幣安永續」runs the Binance perp-futures
desk. Each tab has its own agent, conversation context, system prompt, and tool set — the two
never mix. Type a research question; the agent streams each tool call live and any charts it
makes appear inline in the thread. Needs the local model server (scripts/serve_local.sh).
gradio is imported lazily so the streaming helpers stay testable.
"""

from __future__ import annotations

import os
import queue
import threading
from functools import partial

from optionpilot.agent.approval import auto_spend
from optionpilot.agent.profiles import CRYPTO_PROFILE, OPTIONS_PROFILE, Profile, build_loop
from optionpilot.config import Config


def new_session(profile: Profile) -> dict:
    """A fresh agent for one profile + the event queue its on_event pushes tool activity into."""
    cfg = Config.load()
    events: queue.Queue = queue.Queue()
    # interactive=False: in the GUI, ask_user must never block on terminal input
    loop = build_loop(cfg, profile, approve_spend=auto_spend, interactive=False,
                      on_event=lambda kind, text: events.put((kind, text)))
    return {"loop": loop, "events": events, "cfg": cfg, "profile": profile}


def stream_run(loop, events, message):
    """Yield the assistant's text as it works: tool calls stream in, then the final verdict."""
    result: dict = {}

    def _run():
        try:
            result["out"] = loop.run(message)
        except Exception as e:  # noqa: BLE001 - surface errors in the UI
            result["out"] = f"⚠️ error: {e}"
        finally:
            events.put(None)  # sentinel

    threading.Thread(target=_run, daemon=True).start()
    steps = ""
    while True:
        ev = events.get()
        if ev is None:
            break
        kind, text = ev
        steps += f"🔧 `{kind}` · {text}\n\n"
        yield steps
    yield (steps + ("\n---\n\n" if steps else "") + result.get("out", "")).strip()


def _chart_paths(cfg) -> set:
    d = cfg.runs_dir / "charts"
    return set(d.glob("*.png")) if d.exists() else set()


def chat_handler(message, history, session, profile: Profile):
    """Stream the agent's text, then append any charts it generated INLINE in the thread."""
    session = session or new_session(profile)
    cfg = session["cfg"]
    before = _chart_paths(cfg)
    base = list(history or []) + [{"role": "user", "content": message}]

    text = ""
    for text in stream_run(session["loop"], session["events"], message):
        yield base + [{"role": "assistant", "content": text}], session

    msgs = base + [{"role": "assistant", "content": text}]
    for p in sorted(_chart_paths(cfg) - before, key=lambda p: p.stat().st_mtime):
        msgs.append({"role": "assistant", "content": {"path": str(p)}})  # image bubble
    yield msgs, session


_EXAMPLES = {
    "options": [
        "你有哪些工具?",
        "研究 ZETA 的 wheel 策略並畫出圖表,2024-07-01 到 2026-06-18",
        "ZETA 近期支撐位在多少?",
        "ZETA 賣 cash-secured put 值得嗎?跟買進持有比並畫權益曲線",
    ],
    "crypto": [
        "你有哪些工具?",
        "分析 NOKUSDT 的資金費率 carry",
        "回測 BTCUSDT 的網格機器人,用 1 小時 K 線",
        "AAPLUSDT 適合做網格嗎?跟買進持有比較",
    ],
}


def _make_tab(gr, profile: Profile):
    """Build one isolated desk tab (its own chatbot + session State + handler)."""
    with gr.Tab(profile.label):
        gr.Markdown(f"**{profile.label}** — {profile.blurb}", elem_id="op-blurb")
        chatbot = gr.Chatbot(height="70vh", show_label=False, render_markdown=True,
                             elem_classes=["op-chat"])
        session = gr.State()
        with gr.Row(equal_height=True):
            msg = gr.Textbox(placeholder=_EXAMPLES[profile.key][1], show_label=False,
                             container=False, scale=8)
            send = gr.Button("傳送", variant="primary", scale=1, min_width=72)
        gr.Examples(examples=_EXAMPLES[profile.key], inputs=msg)

        def _bind(trigger):
            trigger(partial(chat_handler, profile=profile),
                    [msg, chatbot, session], [chatbot, session]).then(lambda: "", None, msg)
        _bind(msg.submit)
        _bind(send.click)


# Mobile-friendly: full width, no wasted padding, hide the Gradio footer, condense the header.
_MOBILE_CSS = """
.gradio-container { max-width: 100% !important; padding: 6px !important; }
footer { display: none !important; }
#op-header { margin: 4px 0 8px !important; }
#op-blurb { margin: 2px 0 6px !important; font-size: 0.9rem; }
@media (max-width: 640px) {
  .gradio-container { padding: 4px !important; }
  #op-header h1 { font-size: 1.25rem !important; }
}
"""


def build_app():
    import gradio as gr

    with gr.Blocks(title="OptionPilot", fill_height=True) as app:
        gr.Markdown("# 🛞 OptionPilot — 兩個獨立研究台(股票期權 / 幣安永續)", elem_id="op-header")
        with gr.Tabs():
            _make_tab(gr, OPTIONS_PROFILE)
            _make_tab(gr, CRYPTO_PROFILE)
    return app


def _ui_auth(cred: str | None):
    """Parse OPTIONPILOT_UI_AUTH='user:pass' into a (user, pass) tuple for Gradio's built-in basic
    auth — a second lock behind Cloudflare Access when the UI is exposed publicly. None when unset
    or malformed (then there's no app-level auth; rely on Cloudflare Access)."""
    if cred and ":" in cred:
        user, pw = cred.split(":", 1)
        if user and pw:
            return (user, pw)
    return None


def main():
    import gradio as gr

    build_app().launch(server_name="0.0.0.0", server_port=7860, theme=gr.themes.Soft(),
                       css=_MOBILE_CSS, auth=_ui_auth(os.getenv("OPTIONPILOT_UI_AUTH")))


if __name__ == "__main__":
    main()
