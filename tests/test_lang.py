"""OpenCC Simplified -> Traditional conversion (forces Traditional Chinese output)."""

from optionpilot.agent.lang import to_traditional


def test_simplified_to_traditional():
    assert to_traditional("这个策略没有优势") == "這個策略沒有優勢"
    assert to_traditional("数据显示风险") == "資料顯示風險"  # s2twp Taiwan localization


def test_passthrough_english_and_traditional():
    assert to_traditional("Sharpe 0.65, max drawdown -23%") == "Sharpe 0.65, max drawdown -23%"
    assert to_traditional("這個已經是繁體") == "這個已經是繁體"
