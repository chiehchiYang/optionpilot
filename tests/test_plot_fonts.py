"""Tests for cross-platform CJK font selection in plots.py (no rendering)."""

from optionpilot.plots import _pick_cjk


def test_picks_macos_font_when_present():
    assert _pick_cjk({"PingFang TC", "DejaVu Sans"}) == "PingFang TC"


def test_picks_linux_font_when_present():
    assert _pick_cjk({"Noto Sans CJK TC", "DejaVu Sans"}) == "Noto Sans CJK TC"


def test_prefers_traditional_over_simplified():
    # both a TC and an SC face installed -> the TC one wins (we output Traditional Chinese)
    assert _pick_cjk({"PingFang SC", "Noto Sans CJK TC"}) == "Noto Sans CJK TC"


def test_none_when_no_cjk_font():
    assert _pick_cjk({"DejaVu Sans", "Arial"}) is None
