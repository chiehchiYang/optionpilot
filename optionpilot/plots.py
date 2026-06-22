"""Chart generation (matplotlib, headless Agg) — clean, modern, CJK-aware.

Each function saves a PNG and returns its path. Callers pass already-computed series so the
plotters stay trivially testable; make_charts does the data wrangling.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless — no display needed
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.font_manager as fm  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

# Use a Traditional-Chinese-capable font if present, so CJK titles aren't tofu boxes.
_CJK = next((n for n in ("Noto Sans CJK TC", "Noto Sans CJK SC", "WenQuanYi Zen Hei",
                         "Droid Sans Fallback")
             if n in {f.name for f in fm.fontManager.ttflist}), None)

plt.rcParams.update({
    "font.family": ([_CJK] if _CJK else []) + ["DejaVu Sans"],
    "font.size": 11,
    "axes.unicode_minus": False,
    "axes.titlesize": 13.5, "axes.titleweight": "bold", "axes.titlepad": 12,
    "axes.labelcolor": "#475569", "axes.labelsize": 10,
    "axes.edgecolor": "#e2e8f0", "axes.linewidth": 1.0,
    "xtick.color": "#64748b", "ytick.color": "#64748b",
    "xtick.labelsize": 9, "ytick.labelsize": 9,
    "grid.color": "#eef2f6", "grid.linewidth": 1.0,
    "figure.facecolor": "white", "axes.facecolor": "white", "savefig.facecolor": "white",
})

_BLUE, _GREEN, _GREY, _PINK, _RED = "#2563eb", "#16a34a", "#94a3b8", "#db2777", "#ef4444"


def _new():
    fig, ax = plt.subplots(figsize=(9, 4.0))
    ax.grid(True, axis="y")
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    return fig, ax


def _datefmt(ax):
    loc = mdates.AutoDateLocator()
    ax.xaxis.set_major_locator(loc)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(loc))


def _finish(fig, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return str(path)


def price_trend(ticker: str, dates, prices, path: Path) -> str:
    fig, ax = _new()
    ax.plot(dates, prices, color=_BLUE, lw=2.0)
    ax.fill_between(dates, prices, min(prices), color=_BLUE, alpha=0.06)
    ax.set_title(f"{ticker} · 標的價格趨勢")
    ax.set_ylabel("價格 ($)")
    _datefmt(ax)
    return _finish(fig, path)


def equity_vs_buyhold(ticker: str, dates, strat_equity, bh_equity, path: Path,
                      strategy: str = "策略") -> str:
    fig, ax = _new()
    ax.plot(dates, strat_equity, color=_GREEN, lw=2.2, label=strategy)
    ax.plot(dates, bh_equity, color=_GREY, lw=1.8, ls="--", label="買進持有")
    ax.axhline(1.0, color="#cbd5e1", lw=0.8)
    ax.set_title(f"{ticker} · 策略權益曲線 vs 買進持有")
    ax.set_ylabel("$1 成長倍數")
    ax.legend(loc="best", frameon=False, fontsize=9)
    _datefmt(ax)
    return _finish(fig, path)


def iv_vs_realized(ticker: str, dates, iv, realized_vol: float, path: Path) -> str:
    fig, ax = _new()
    ax.plot(dates, [v * 100 for v in iv], color=_PINK, lw=2.0, label="隱含波動率 (ATM)")
    ax.axhline(realized_vol * 100, color="#64748b", ls="--", lw=1.4,
               label=f"實際波動率 {realized_vol:.0%}")
    ax.set_title(f"{ticker} · 隱含波動率 vs 實際波動率")
    ax.set_ylabel("年化波動率 (%)")
    ax.legend(loc="best", frameon=False, fontsize=9)
    _datefmt(ax)
    return _finish(fig, path)


def volume_and_pcr(ticker: str, dates, volume, pcr, path: Path) -> str:
    fig, ax1 = _new()
    ax1.bar(dates, volume, color="#bfdbfe", width=1.0, label="期權成交量")
    ax1.set_ylabel("期權成交量", color=_BLUE)
    ax2 = ax1.twinx()
    ax2.plot(dates, pcr, color=_RED, lw=1.6, label="put/call ratio")
    ax2.set_ylabel("put/call ratio", color=_RED)
    ax2.spines["top"].set_visible(False)
    ax1.set_title(f"{ticker} · 期權成交量 + put/call ratio")
    _datefmt(ax1)
    return _finish(fig, path)
