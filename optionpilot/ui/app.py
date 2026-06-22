"""Gradio chat interface for OptionPilot's ml-intern (ChatGPT-style).

Type a research question; the intern runs its methodology (measure_vrp -> backtest ->
walk-forward -> verdict) and the chat streams each tool call live, then the honest conclusion.
Needs the local model server running (scripts/serve_local.sh) and, for free data, the
ThetaData terminal (docs/thetadata_setup.md). gradio is imported lazily so the streaming
helpers stay unit-testable without it.
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
    """A fresh agent + an event queue its on_event pushes tool activity into."""
    cfg = Config.load()
    router = ToolRouter()
    # interactive=False: in the GUI, ask_user must never block on terminal input
    register_default_tools(router, cfg, approve_spend=auto_spend, interactive=False)
    events: queue.Queue = queue.Queue()
    loop = ExperimentLoop(cfg, router, on_event=lambda kind, text: events.put((kind, text)))
    return {"loop": loop, "events": events}


def stream_run(loop, events, message):
    """Yield the assistant's text as it works: tool calls stream in, then the final verdict.

    The agent runs in a thread; its on_event activity is read off the queue and accumulated.
    """
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


# Module-level session: a new conversation (empty history) starts a fresh agent loop.
_SESSION: dict = {}


def chat_fn(message, history):
    if not history or "bundle" not in _SESSION:
        _SESSION["bundle"] = new_session()
    bundle = _SESSION["bundle"]
    yield from stream_run(bundle["loop"], bundle["events"], message)


def build_app():
    import gradio as gr

    return gr.ChatInterface(
        fn=chat_fn,
        title="🛞 OptionPilot — 期權策略研究 intern",
        description=(
            "問一個研究問題,它會自己跑方法論(measure_vrp → 回測 → walk-forward → 誠實結論)"
            "並即時顯示每個工具呼叫。需先啟動本地模型(`scripts/serve_local.sh`)。"
        ),
        examples=[
            "研究 ZETA 的 wheel 策略,2024-07-01 到 2026-06-18",
            "ZETA 賣 cash-secured put 值得嗎?跟買進持有比",
            "ZETA 的 IV 相對下檔波動高估嗎?(measure_vrp)",
        ],
    )


def main():
    build_app().launch(server_name="0.0.0.0", server_port=7860)


if __name__ == "__main__":
    main()
