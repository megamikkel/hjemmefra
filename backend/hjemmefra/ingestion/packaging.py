"""Deterministic parsing of package sizes from product titles, e.g. '2 x 400 g', '1,5 l', '10 stk'."""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Optional, Tuple

from hjemmefra.core.units import Unit, UnknownUnit, parse_unit

_RE = re.compile(r"(?:(\d+)\s*[xX×]\s*)?(\d+(?:[.,]\d+)?)\s*(kg|g|gram|ml|cl|dl|l|ltr|liter|stk|stk\.|pk|pakke|ps)\b", re.IGNORECASE)


def parse_package(text: str) -> Optional[Tuple[Decimal, Unit, int]]:
    """Return (quantity, unit, count) or None if no unambiguous package size is found."""
    matches = _RE.findall(text or "")
    if len(matches) != 1:
        return None
    count, qty, unit = matches[0]
    try:
        u = parse_unit(unit)
    except UnknownUnit:
        return None
    return Decimal(qty.replace(",", ".")), u, int(count) if count else 1
