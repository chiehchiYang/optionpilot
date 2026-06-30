"""Tests for per-user identity + conversation persistence helpers (no Gradio runtime needed)."""

from optionpilot.ui.app import _conv_path, _load_conv, _save_conv, _slug, _user_id


class _Req:
    def __init__(self, headers=None, username=None):
        self.headers = headers or {}
        if username is not None:
            self.username = username


def test_user_id_prefers_cloudflare_access_email():
    r = _Req(headers={"cf-access-authenticated-user-email": "alice@example.com"})
    assert _user_id(r) == "alice@example.com"


def test_user_id_falls_back_to_username_then_local():
    assert _user_id(_Req(username="bob")) == "bob"
    assert _user_id(_Req()) == "local"
    assert _user_id(None) == "local"


def test_user_id_has_no_path_separators():
    r = _Req(headers={"cf-access-authenticated-user-email": "../../etc@x"})
    assert "/" not in _user_id(r)


def test_slug_blank_is_local():
    assert _slug("") == "local"
    assert _slug("a b/c") == "a_b_c"


def test_two_users_get_different_conversation_paths(tmp_path):
    class _Cfg:
        pass

    a, b = _Cfg(), _Cfg()
    a.runs_dir = tmp_path / "users" / "alice@example.com"
    b.runs_dir = tmp_path / "users" / "bob@example.com"
    assert _conv_path(a, "options") != _conv_path(b, "options")


def test_conv_save_load_roundtrip_incl_image_bubbles(tmp_path):
    p = tmp_path / "conversation_options.json"
    msgs = [{"role": "user", "content": "hi"},
            {"role": "assistant", "content": "answer"},
            {"role": "assistant", "content": {"path": "/runs/charts/x.png"}}]
    _save_conv(p, msgs)
    assert _load_conv(p) == msgs


def test_load_missing_returns_empty(tmp_path):
    assert _load_conv(tmp_path / "nope.json") == []
