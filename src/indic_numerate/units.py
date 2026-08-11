"""Unit normalisation. Pure functions, no I/O, no state.

This is where the interesting failures live, so it carries the most test
coverage in the repo (tests/test_units.py). Two families exist and they do not
mix: monetary magnitudes (rupees .. billion) and dimensionless quantities
(percent, ratio, days, count). Crossing families raises rather than guessing.

Everything is Decimal. Binary floats cannot represent 1e5 * 1.1 exactly and a
benchmark that scores to a tolerance must not lose digits to its own arithmetic.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

# Multipliers into base rupees.
MONETARY_FACTORS: dict[str, Decimal] = {
    "rupees": Decimal(1),
    "thousand": Decimal(10) ** 3,
    "lakh": Decimal(10) ** 5,
    "million": Decimal(10) ** 6,
    "crore": Decimal(10) ** 7,
    "billion": Decimal(10) ** 9,
}
DIMENSIONLESS = ("percent", "ratio", "days", "count")


class UnitError(ValueError):
    """Raised for any unrecognised or cross-family unit operation."""


# Spelling variants seen in real filings. Longest match wins, so order matters
# only within the alternation built below.
_ALIASES: dict[str, str] = {
    "rs": "rupees", "inr": "rupees", "rupee": "rupees", "rupees": "rupees",
    "thousand": "thousand", "thousands": "thousand", "000s": "thousand", "k": "thousand",
    "lakh": "lakh", "lakhs": "lakh", "lac": "lakh", "lacs": "lakh", "lakhs)": "lakh",
    "crore": "crore", "crores": "crore", "cr": "crore", "crs": "crore",
    "million": "million", "millions": "million", "mn": "million", "mio": "million", "m": "million",
    "billion": "billion", "billions": "billion", "bn": "billion",
    "percent": "percent", "percentage": "percent", "pct": "percent", "%": "percent",
    "bps": "bps",
    "ratio": "ratio", "times": "ratio", "x": "ratio",
    "days": "days", "day": "days",
    "count": "count", "nos": "count", "number": "count",
}
_TOKEN_RE = re.compile(r"[a-z%]+|\d+s|%")


def parse_unit(text: str) -> str:
    """Normalise a unit string from a table header or a model's answer.

    Handles the shapes filings actually print: 'Rs. in lakhs', '(INR crore)',
    'Rupees in Millions', '%'. Currency words are ignored when a magnitude word
    is present, because 'Rs. in crore' is a crore, not a rupee.
    """
    if not isinstance(text, str) or not text.strip():
        raise UnitError(f"cannot parse unit from {text!r}: empty")
    lowered = text.lower().replace("₹", " rs ").replace("`", " rs ").replace("per cent", "percent")
    tokens = _TOKEN_RE.findall(lowered.replace("%", " % "))
    found = [_ALIASES[t] for t in tokens if t in _ALIASES]
    if not found:
        raise UnitError(
            f"cannot parse unit from {text!r}: no known unit token "
            f"(expected one of {', '.join(sorted(set(_ALIASES.values())))})"
        )
    non_currency = [f for f in found if f != "rupees"]
    unit = non_currency[0] if non_currency else "rupees"
    if unit == "bps":
        return "bps"
    return unit


def family(unit: str) -> str:
    if unit in MONETARY_FACTORS:
        return "monetary"
    if unit in DIMENSIONLESS or unit == "bps":
        return "dimensionless"
    raise UnitError(
        f"unknown unit {unit!r}; expected one of "
        f"{', '.join(sorted(set(MONETARY_FACTORS) | set(DIMENSIONLESS)))}"
    )


def to_base(value: Decimal | int | str, unit: str) -> Decimal:
    """Monetary -> rupees. percent/bps -> ratio. days/count/ratio unchanged."""
    v = Decimal(str(value))
    fam = family(unit)
    if fam == "monetary":
        return v * MONETARY_FACTORS[unit]
    if unit == "percent":
        return v / Decimal(100)
    if unit == "bps":
        return v / Decimal(10000)
    return v


def convert(value: Decimal | int | str, from_unit: str, to_unit: str) -> Decimal:
    """Convert within a family. Crossing families raises."""
    f_from, f_to = family(from_unit), family(to_unit)
    if f_from != f_to:
        raise UnitError(
            f"cannot convert {from_unit} ({f_from}) to {to_unit} ({f_to}): "
            "monetary magnitudes and dimensionless quantities are different families"
        )
    base = to_base(value, from_unit)
    if f_to == "monetary":
        return base / MONETARY_FACTORS[to_unit]
    if to_unit == "percent":
        return base * Decimal(100)
    if to_unit == "bps":
        return base * Decimal(10000)
    if to_unit in ("days", "count") and from_unit != to_unit:
        raise UnitError(f"cannot convert {from_unit} to {to_unit}: not commensurable")
    return base


# --------------------------------------------------------------------------
# Fiscal periods. FY2023 = year ended 31 March 2023 (Indian convention).
# --------------------------------------------------------------------------

_PERIOD_RE = re.compile(r"^(?:(q[1-4])\s*)?(fy|cy)\s*'?(\d{2}|\d{4})(?:\s*[-/]\s*(\d{2}|\d{4}))?$")
_SPAN_RE = re.compile(r"^(\d{4})\s*[-/]\s*(\d{2}|\d{4})$")


def parse_period(text: str) -> str:
    """Canonicalise a period label to FY2023 / CY2022 / Q3FY2024.

    Accepts the forms filings and models actually use: 'FY23', 'FY 2022-23',
    '2022-23', 'fy2023', 'Q3 FY24', 'CY2022'. '2022-23' is an Indian fiscal
    span and canonicalises to FY2023 -- the *later* year, which is the single
    most common off-by-one in this domain.
    """
    if not isinstance(text, str) or not text.strip():
        raise UnitError(f"cannot parse period from {text!r}: empty")
    t = text.strip().lower().replace("_", "-")
    span = _SPAN_RE.match(t)
    if span:
        start, end = span.groups()
        end_year = int(end) if len(end) == 4 else int(start[:2] + end)
        if end_year != int(start) + 1:
            raise UnitError(f"cannot parse period from {text!r}: {start}-{end} is not consecutive")
        return f"FY{end_year}"
    m = _PERIOD_RE.match(t)
    if not m:
        raise UnitError(
            f"cannot parse period from {text!r}: expected FY2023, CY2022, Q3FY2024 or 2022-23"
        )
    quarter, basis, year, second = m.groups()
    y = int(year) if len(year) == 4 else 2000 + int(year)
    if second is not None:
        end_year = int(second) if len(second) == 4 else (y // 100) * 100 + int(second)
        if end_year != y + 1:
            raise UnitError(f"cannot parse period from {text!r}: years are not consecutive")
        y = end_year
    return f"{quarter.upper() if quarter else ''}{basis.upper()}{y}"


def period_window(period: str) -> tuple[date, date]:
    """Inclusive (start, end) dates covered by a canonical period label."""
    p = parse_period(period)
    quarter, rest = (p[:2], p[2:]) if p.startswith("Q") else ("", p)
    basis, year = rest[:2], int(rest[2:])
    if basis == "CY":
        if quarter:
            q = int(quarter[1])
            start = date(year, 3 * (q - 1) + 1, 1)
            end_month = 3 * q
            return start, date(year, end_month, _last_day(year, end_month))
        return date(year, 1, 1), date(year, 12, 31)
    # FY<Y> runs 1 April <Y-1> to 31 March <Y>.
    if quarter:
        q = int(quarter[1])
        start_month = 4 + 3 * (q - 1)
        start_year = year - 1 if start_month <= 12 else year
        if start_month > 12:
            start_month -= 12
        start = date(start_year, start_month, 1)
        end_month = start_month + 2
        end_year = start_year
        if end_month > 12:
            end_month -= 12
            end_year += 1
        return start, date(end_year, end_month, _last_day(end_year, end_month))
    return date(year - 1, 4, 1), date(year, 3, 31)


def _last_day(year: int, month: int) -> int:
    if month == 12:
        return 31
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    return (nxt - date(year, month, 1)).days


def same_period(a: str, b: str) -> bool:
    """True only if the two labels denote the identical window.

    FY2023 and CY2023 are NOT the same period; this is the FY-vs-CY trap and it
    is the one comparison the units axis exists to catch.
    """
    return period_window(a) == period_window(b)
