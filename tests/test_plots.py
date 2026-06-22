"""Tests for chart generation (each plotter saves a PNG)."""

from datetime import date, timedelta

from optionpilot import plots


def _dates(n):
    return [date(2024, 1, 1) + timedelta(days=k) for k in range(n)]


def test_price_trend_saves_png(tmp_path):
    p = plots.price_trend("ZETA", _dates(5), [10, 11, 12, 11, 13], tmp_path / "price.png")
    assert (tmp_path / "price.png").exists() and p.endswith(".png")


def test_equity_vs_buyhold_saves_png(tmp_path):
    d = _dates(4)
    p = plots.equity_vs_buyhold("ZETA", d, [1, 1.02, 1.01, 1.05], [1, 1.1, 1.2, 1.3],
                                tmp_path / "eq.png", "cash_secured_put")
    assert (tmp_path / "eq.png").exists()


def test_iv_vs_realized_saves_png(tmp_path):
    p = plots.iv_vs_realized("ZETA", _dates(3), [0.5, 0.55, 0.52], 0.48, tmp_path / "iv.png")
    assert (tmp_path / "iv.png").exists()


def test_volume_and_pcr_saves_png(tmp_path):
    p = plots.volume_and_pcr("ZETA", _dates(3), [100, 200, 150], [0.5, 0.8, 0.6],
                             tmp_path / "vol.png")
    assert (tmp_path / "vol.png").exists()
