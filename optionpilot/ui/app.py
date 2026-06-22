"""Gradio chat UI for OptionPilot's ml-intern — chat on the left, generated charts on the right.

Type a research question; the intern runs its methodology (measure_vrp -> backtest ->
walk-forward -> verdict), streams each tool call live, and any charts it makes (make_charts)
appear in the gallery. Needs the local model server (scripts/serve_local.sh) and, for free
data, the ThetaData terminal. gradio is imported lazily so the streaming helpers stay testable.
"""

from __future__ import annotations

import queue
import threading

from optionpilot.agent.approval import auto_spend
from optionpilot.agent.loop import ExperimentLoop
from optionpilot.agent.router import ToolRouter
from optionpilot.config import Config
from optionpilot.tools import register_default_tools


def new_session() -> dict:
    """A fresh agent + the event queue its on_event pushes tool activity into."""
    cfg = Config.load()
    router = ToolRouter()
    # interactive=False: in the GUI, ask_user must never block on terminal input
    register_default_tools(router, cfg, approve_spend=auto_spend, interactive=False)
    events: queue.Queue = queue.Queue()
    loop = ExperimentLoop(cfg, router, on_event=lambda kind, text: events.put((kind, text)))
    return {"loop": loop, "events": events, "cfg": cfg}


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


def chat_handler(message, history, session):
    """Stream the intern's text, then append any charts it generated INLINE in the thread."""
    session = session or new_session()
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


def build_app():
    import gradio as gr

    with gr.Blocks(title="OptionPilot — ml-intern") as app:
        gr.Markdown(
            "# 🛞 OptionPilot — 期權策略研究 intern\n"
            "問一個研究問題,它自己跑方法論(measure_vrp → 回測 → walk-forward),"
            "即時顯示工具呼叫,圖表直接出現在對話裡。需先啟動本地模型。\n"
            "_想知道能做什麼?問「**你有哪些工具?**」_"
        )
        chatbot = gr.Chatbot(height=600, show_label=False, render_markdown=True)
        session = gr.State()
        msg = gr.Textbox(placeholder="例:研究 ZETA 的 wheel 策略並畫圖,2024-07-01 到 2026-06-18",
                         show_label=False, autofocus=True)
        gr.Examples(
            examples=[
                "你有哪些工具?",
                "研究 ZETA 的 wheel 策略並畫出圖表,2024-07-01 到 2026-06-18",
                "ZETA 近期支撐位在多少?",
                "ZETA 賣 cash-secured put 值得嗎?跟買進持有比並畫權益曲線",
            ],
            inputs=msg,
        )
        msg.submit(chat_handler, [msg, chatbot, session], [chatbot, session]).then(
            lambda: "", None, msg
        )
    return app


def main():
    import gradio as gr

    build_app().launch(server_name="0.0.0.0", server_port=7860, theme=gr.themes.Soft())


if __name__ == "__main__":
    main()
