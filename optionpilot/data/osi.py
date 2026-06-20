"""Parse OSI (Options Symbology Initiative) contract symbols.

OSI format is fixed 21 chars: 6-char root (space-padded) + YYMMDD + C/P + 8-digit strike
in thousandths of a dollar. Databento OPRA emits this, e.g. "NOK   230113C00005000"
= NOK, expiry 2023-01-13, Call, strike $5.000.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

_OSI_RE = re.compile(r"^([A-Za-z][A-Za-z0-9]*)\s*(\d{6})([CP])(\d{8})$")


@dataclass(frozen=True)
class OptionContract:
    root: str
    expiry: date
    kind: str  # 'C' or 'P'
    strike: float

    @property
    def is_call(self) -> bool:
        return self.kind == "C"

    @property
    def is_put(self) -> bool:
        return self.kind == "P"


def parse_osi(symbol: str) -> OptionContract:
    """Parse one OSI symbol. Raises ValueError on malformed input."""
    m = _OSI_RE.match(symbol.strip())
    if not m:
        raise ValueError(f"not a valid OSI symbol: {symbol!r}")
    root, ymd, cp, strike = m.groups()
    yy, mm, dd = int(ymd[:2]), int(ymd[2:4]), int(ymd[4:6])
    try:
        expiry = date(2000 + yy, mm, dd)
    except ValueError as e:
        raise ValueError(f"bad expiry in OSI symbol {symbol!r}: {e}") from e
    return OptionContract(root=root, expiry=expiry, kind=cp, strike=int(strike) / 1000.0)


def try_parse_osi(symbol: str) -> OptionContract | None:
    """Like parse_osi but returns None instead of raising."""
    try:
        return parse_osi(symbol)
    except ValueError:
        return None
