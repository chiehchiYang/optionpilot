"""Summarize a stock's RECENT fundamentals into trends — pure logic, no network.

Fundamentals here are CONTEXT, not a buy/sell signal: the recent trajectory of revenue/earnings,
the direction of margins, and the valuation snapshot tell you what kind of business you're looking
at. Turning any of it into a trade still has to go through the backtest tools (and mind that IV
balloons around earnings dates — see next_earnings).
"""

from __future__ import annotations


def _growth(newest, older):
    if newest is None or older is None or older == 0:
        return None
    return round(newest / older - 1.0, 4)


def summarize_fundamentals(quarterly: list[dict], snapshot: dict | None = None,
                           next_earnings: str | None = None) -> dict:
    """quarterly: list (oldest->newest) of {period, revenue, gross_profit, operating_income,
    net_income, diluted_eps}. Returns per-quarter margins + YoY/QoQ growth + margin trend +
    the valuation snapshot."""
    rows = []
    for q in quarterly:
        rev = q.get("revenue")
        r = {"period": q.get("period"), "revenue": rev, "net_income": q.get("net_income"),
             "diluted_eps": q.get("diluted_eps")}
        if rev:
            gp, oi, ni = q.get("gross_profit"), q.get("operating_income"), q.get("net_income")
            r["gross_margin"] = round(gp / rev, 4) if gp is not None else None
            r["operating_margin"] = round(oi / rev, 4) if oi is not None else None
            r["net_margin"] = round(ni / rev, 4) if ni is not None else None
        rows.append(r)

    def series(key):
        return [q.get(key) for q in quarterly]

    rev_s, ni_s = series("revenue"), series("net_income")
    yoy_rev = _growth(rev_s[-1], rev_s[-5]) if len(rev_s) >= 5 else None
    yoy_ni = _growth(ni_s[-1], ni_s[-5]) if len(ni_s) >= 5 else None
    qoq_rev = _growth(rev_s[-1], rev_s[-2]) if len(rev_s) >= 2 else None
    qoq_ni = _growth(ni_s[-1], ni_s[-2]) if len(ni_s) >= 2 else None

    nm = [r["net_margin"] for r in rows if r.get("net_margin") is not None]
    margin_trend = None
    if len(nm) >= 2:
        margin_trend = ("improving" if nm[-1] > nm[0]
                        else "declining" if nm[-1] < nm[0] else "flat")

    return {
        "quarters": rows,
        "revenue_yoy": yoy_rev, "net_income_yoy": yoy_ni,
        "revenue_qoq": qoq_rev, "net_income_qoq": qoq_ni,
        "net_margin_trend": margin_trend,
        "snapshot": snapshot or {},
        "next_earnings": next_earnings,
        "note": ("基本面是 CONTEXT,不是買賣訊號:看近幾季營收/獲利趨勢與利潤率走向、估值快照。"
                 "要變成交易想法仍須回測驗證;留意 next_earnings —— 財報前後 IV 會爆。"),
    }
