"""Tests for the optional Gradio basic-auth parsing (OPTIONPILOT_UI_AUTH)."""

from optionpilot.ui.app import _ui_auth


def test_none_or_blank_means_no_auth():
    assert _ui_auth(None) is None
    assert _ui_auth("") is None


def test_valid_user_pass():
    assert _ui_auth("alice:secret") == ("alice", "secret")


def test_password_may_contain_colons():
    assert _ui_auth("alice:a:b:c") == ("alice", "a:b:c")   # split once


def test_malformed_means_no_auth():
    assert _ui_auth("nocolon") is None
    assert _ui_auth("user:") is None       # blank password
    assert _ui_auth(":pass") is None       # blank user
