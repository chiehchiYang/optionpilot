"""Force Traditional Chinese output (Qwen tends to emit Simplified).

OpenCC s2twp converts Simplified -> Taiwan Traditional; English/numbers/already-Traditional
text pass through unchanged, so it is safe to apply to any final answer. Degrades to a no-op
if OpenCC is not installed.
"""

from __future__ import annotations

_cc = None  # None = not tried, False = unavailable, else an OpenCC converter


def to_traditional(text: str) -> str:
    global _cc
    if _cc is None:
        try:
            from opencc import OpenCC
            _cc = OpenCC("s2twp")
        except Exception:  # noqa: BLE001 - optional dependency
            _cc = False
    if not _cc or not text:
        return text
    try:
        return _cc.convert(text)
    except Exception:  # noqa: BLE001
        return text
