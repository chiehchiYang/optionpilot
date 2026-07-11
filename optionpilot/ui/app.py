"""Gradio chat UI for OptionPilot — two ISOLATED desks as tabs.

Tab「股票期權」runs the options-research intern; tab「幣安永續」runs the Binance perp-futures
desk. Each tab has its own agent, conversation context, system prompt, and tool set — the two
never mix. Type a research question; the agent streams each tool call live and any charts it
makes appear inline in the thread.

Per-user: when exposed behind Cloudflare Access, each logged-in person gets their OWN persistent
conversation + isolated runs (memory / experiments / trajectories), keyed by their Access email —
so restarts don't lose history and two people don't share a thread.
"""

from __future__ import annotations

import json
import os
import queue
import re
import threading

import gradio as gr

from optionpilot.agent.approval import auto_spend
from optionpilot.agent.profiles import CRYPTO_PROFILE, OPTIONS_PROFILE, Profile, build_loop
from optionpilot.config import Config


def _slug(s: str) -> str:
    """Filesystem-safe id (no path separators)."""
    return re.sub(r"[^A-Za-z0-9_.@-]", "_", s or "")[:120] or "local"


def _user_id(request) -> str:
    """Stable per-user id for isolating conversations + runs. Prefers the Cloudflare Access identity
    (Cf-Access-Authenticated-User-Email), falls back to a basic-auth username, else 'local' (no
    auth / single-user)."""
    email = None
    if request is not None:
        headers = getattr(request, "headers", None)
        if headers is not None:
            try:
                email = headers.get("cf-access-authenticated-user-email")
            except Exception:  # noqa: BLE001
                email = None
        email = email or getattr(request, "username", None)
    return _slug(email or "local")


def _user_config(uid: str) -> Config:
    """A Config whose runs_dir is namespaced to one user, so memory / trajectories / experiments /
    charts / the saved transcript are all isolated per logged-in person."""
    base = Config.load()
    cfg = Config(**{**base.__dict__, "runs_dir": base.runs_dir / "users" / uid})
    cfg.runs_dir.mkdir(parents=True, exist_ok=True)
    return cfg


def _conv_path(cfg: Config, desk: str):
    return cfg.runs_dir / f"conversation_{desk}.json"


def _save_conv(path, messages) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(messages, ensure_ascii=False), encoding="utf-8")
    except Exception:  # noqa: BLE001 - persistence is best-effort, must never break the chat
        pass


def _load_conv(path) -> list:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    except Exception:  # noqa: BLE001
        return []


def new_session(profile: Profile, uid: str = "local") -> dict:
    """A fresh agent for one profile + the event queue its on_event pushes tool activity into.
    Runs are namespaced to `uid` so two logged-in people don't share memory/experiments."""
    cfg = _user_config(uid)
    events: queue.Queue = queue.Queue()
    # interactive=False: in the GUI, ask_user must never block on terminal input
    loop = build_loop(cfg, profile, approve_spend=auto_spend, interactive=False,
                      on_event=lambda kind, text: events.put((kind, text)))
    return {"loop": loop, "events": events, "cfg": cfg, "profile": profile, "uid": uid}


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
    status = ""       # a single LIVE line (e.g. ThetaData fetch progress), replaced not appended
    while True:
        ev = events.get()
        if ev is None:
            break
        kind, text = ev
        if kind == "progress":
            status = f"\n⏳ {text}"
        else:
            steps += f"🔧 `{kind}` · {text}\n\n"
            status = ""
        yield (steps + status).strip()
    yield (steps + ("\n---\n\n" if steps else "") + result.get("out", "")).strip()


def _chart_paths(cfg) -> set:
    d = cfg.runs_dir / "charts"
    return set(d.glob("*.png")) if d.exists() else set()


def chat_handler(message, history, session, profile: Profile, request: gr.Request = None):
    """Stream the agent's text, append any charts INLINE, then PERSIST the per-user transcript."""
    if session is None:
        session = new_session(profile, _user_id(request))
    cfg = session["cfg"]
    before = _chart_paths(cfg)
    base = list(history or []) + [{"role": "user", "content": message}]

    text = ""
    for text in stream_run(session["loop"], session["events"], message):
        yield base + [{"role": "assistant", "content": text}], session

    msgs = base + [{"role": "assistant", "content": text}]
    for p in sorted(_chart_paths(cfg) - before, key=lambda p: p.stat().st_mtime):
        msgs.append({"role": "assistant", "content": {"path": str(p)}})  # image bubble
    _save_conv(_conv_path(cfg, profile.key), msgs)   # survives restart + isolated per user
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


def _make_tab(profile: Profile):
    """One isolated desk tab. Returns (chatbot, session, on_load) so build_app can restore the
    logged-in user's saved transcript when the page opens."""
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

        def _on_submit(message, history, sess, request: gr.Request):
            yield from chat_handler(message, history, sess, profile, request)

        for trigger in (msg.submit, send.click):
            trigger(_on_submit, [msg, chatbot, session], [chatbot, session]).then(
                lambda: "", None, msg)

    def _on_load(request: gr.Request):
        """On page open: create the user's session + restore their saved transcript."""
        try:
            sess = new_session(profile, _user_id(request))
            return _load_conv(_conv_path(sess["cfg"], profile.key)), sess
        except Exception:  # noqa: BLE001 - never block the page; session lazy-creates on 1st msg
            return [], None

    return chatbot, session, _on_load


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
    with gr.Blocks(title="OptionPilot", fill_height=True) as app:
        gr.Markdown("# 🛞 OptionPilot — 兩個獨立研究台(股票期權 / 幣安永續)", elem_id="op-header")
        with gr.Tabs():
            opt_cb, opt_st, opt_load = _make_tab(OPTIONS_PROFILE)
            cry_cb, cry_st, cry_load = _make_tab(CRYPTO_PROFILE)
        # restore each logged-in user's saved transcript when the page opens
        app.load(opt_load, None, [opt_cb, opt_st])
        app.load(cry_load, None, [cry_cb, cry_st])
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


def _raise_open_file_limit(target: int = 8192) -> None:
    """macOS defaults RLIMIT_NOFILE to 256 — too low for Gradio serving its many static assets
    (-> OSError 'Too many open files'). Bump this process's soft limit. Best-effort."""
    try:
        import resource
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        want = target if hard == resource.RLIM_INFINITY else min(target, hard)
        if soft < want:
            resource.setrlimit(resource.RLIMIT_NOFILE, (want, hard))
    except Exception:  # noqa: BLE001 - e.g. Windows has no `resource`; never block startup
        pass


def main():
    _raise_open_file_limit()
    build_app().launch(server_name="0.0.0.0", server_port=7860, theme=gr.themes.Soft(),
                       css=_MOBILE_CSS, auth=_ui_auth(os.getenv("OPTIONPILOT_UI_AUTH")))


if __name__ == "__main__":
    main()
