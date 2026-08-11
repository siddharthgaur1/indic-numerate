"""The unit normaliser gets the most coverage in the repo, by design.

Every raise site in units.py is asserted on, and every message is checked for
naming the offending input -- this is one of the three surfaces an outside user
touches (loader, unit normaliser, submission validator).
"""

from decimal import Decimal

import pytest

from indic_numerate.units import (
    UnitError,
    convert,
    family,
    parse_period,
    parse_unit,
    period_window,
    same_period,
    to_base,
)

# --------------------------------------------------------------------------
# parse_unit
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("crore", "crore"),
        ("Crores", "crore"),
        ("Rs. in crore", "crore"),
        ("Rs. in Crores", "crore"),
        ("(Rs. in Lakhs)", "lakh"),
        ("Rupees in lacs", "lakh"),
        ("INR mn", "million"),
        ("USD-free: Rupees in Millions", "million"),
        ("Rs bn", "billion"),
        ("in thousands", "thousand"),
        ("Rs.", "rupees"),
        ("INR", "rupees"),
        ("%", "percent"),
        ("per cent", "percent"),
        ("percentage points", "percent"),
        ("times", "ratio"),
        ("x", "ratio"),
        ("days", "days"),
        ("nos", "count"),
        ("bps", "bps"),
    ],
)
def test_parse_unit_variants(text, expected):
    assert parse_unit(text) == expected


def test_currency_word_loses_to_magnitude_word():
    # 'Rs. in crore' is a crore, not a rupee. Getting this backwards silently
    # rescales every figure in the table by 1e7.
    assert parse_unit("Rs. in crore") == "crore"
    assert parse_unit("crore of rupees") == "crore"


def test_rupee_sign_and_backtick_are_currency():
    assert parse_unit("₹ lakh") == "lakh"
    assert parse_unit("` crore") == "crore"  # a backtick is a rupee sign in many PDFs


def test_parse_unit_rejects_empty():
    with pytest.raises(UnitError, match="empty"):
        parse_unit("   ")


def test_parse_unit_rejects_non_string():
    with pytest.raises(UnitError, match="empty"):
        parse_unit(None)


def test_parse_unit_names_the_offending_input():
    with pytest.raises(UnitError, match="'furlongs'"):
        parse_unit("furlongs")


# --------------------------------------------------------------------------
# family / to_base / convert
# --------------------------------------------------------------------------


def test_family():
    assert family("crore") == "monetary"
    assert family("percent") == "dimensionless"


def test_family_rejects_unknown_and_lists_valid():
    with pytest.raises(UnitError, match="unknown unit 'parsecs'"):
        family("parsecs")


@pytest.mark.parametrize(
    "value,unit,base",
    [
        (1, "rupees", "1"),
        (1, "thousand", "1000"),
        (1, "lakh", "100000"),
        (1, "million", "1000000"),
        (1, "crore", "10000000"),
        (1, "billion", "1000000000"),
        ("1234.56", "crore", "12345600000.00"),
    ],
)
def test_to_base_monetary(value, unit, base):
    assert to_base(value, unit) == Decimal(base)


def test_to_base_percent_is_a_ratio():
    assert to_base(20, "percent") == Decimal("0.2")
    assert to_base(150, "bps") == Decimal("0.015")


def test_to_base_passthrough():
    assert to_base(45, "days") == Decimal(45)
    assert to_base("1.5", "ratio") == Decimal("1.5")


@pytest.mark.parametrize(
    "value,frm,to,expected",
    [
        (1, "crore", "lakh", "100"),
        (100, "lakh", "crore", "1"),
        (1, "crore", "million", "10"),  # the conversion models most often miss
        (10, "million", "crore", "1"),
        (1, "billion", "crore", "100"),
        ("2.5", "lakh", "rupees", "250000"),
        (1000, "rupees", "thousand", "1"),
        (20, "percent", "ratio", "0.2"),
        ("0.2", "ratio", "percent", "20"),
        (25, "bps", "percent", "0.25"),
    ],
)
def test_convert(value, frm, to, expected):
    assert convert(value, frm, to) == Decimal(expected)


def test_convert_is_exact_not_floaty():
    # 0.1 + 0.2 style drift would break a 0.5% tolerance on a large figure.
    assert convert("0.1", "crore", "lakh") == Decimal("10")
    assert convert(convert("1234.56", "crore", "million"), "million", "crore") == Decimal("1234.56")


def test_convert_identity():
    assert convert("7.25", "lakh", "lakh") == Decimal("7.25")


def test_convert_across_families_raises():
    with pytest.raises(UnitError, match="different families"):
        convert(10, "crore", "percent")
    with pytest.raises(UnitError, match="different families"):
        convert(10, "percent", "crore")


def test_convert_incommensurable_dimensionless_raises():
    with pytest.raises(UnitError, match="not commensurable"):
        convert(10, "percent", "days")


def test_convert_unknown_unit_raises():
    with pytest.raises(UnitError, match="unknown unit 'quintals'"):
        convert(10, "quintals", "crore")


# --------------------------------------------------------------------------
# fiscal periods
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("FY2023", "FY2023"),
        ("fy2023", "FY2023"),
        ("FY23", "FY2023"),
        ("FY '23", "FY2023"),
        ("FY 2022-23", "FY2023"),
        ("FY2022-2023", "FY2023"),
        ("2022-23", "FY2023"),
        ("2022-2023", "FY2023"),
        ("CY2022", "CY2022"),
        ("cy22", "CY2022"),
        ("Q3 FY24", "Q3FY2024"),
        ("q1fy2023", "Q1FY2023"),
    ],
)
def test_parse_period(text, expected):
    assert parse_period(text) == expected


def test_fiscal_span_maps_to_the_later_year():
    # '2022-23' is FY2023, not FY2022. This off-by-one is the single most
    # common fiscal-year error in this domain.
    assert parse_period("2022-23") == "FY2023"


def test_parse_period_rejects_non_consecutive_span():
    with pytest.raises(UnitError, match="not consecutive"):
        parse_period("2020-23")


def test_parse_period_rejects_garbage_and_names_it():
    with pytest.raises(UnitError, match="'sometime last year'"):
        parse_period("sometime last year")


def test_parse_period_rejects_empty():
    with pytest.raises(UnitError, match="empty"):
        parse_period("")


def test_fy_window_is_april_to_march():
    from datetime import date

    assert period_window("FY2023") == (date(2022, 4, 1), date(2023, 3, 31))


def test_cy_window_is_january_to_december():
    from datetime import date

    assert period_window("CY2022") == (date(2022, 1, 1), date(2022, 12, 31))


def test_quarter_windows():
    from datetime import date

    assert period_window("Q1FY2023") == (date(2022, 4, 1), date(2022, 6, 30))
    assert period_window("Q4FY2023") == (date(2023, 1, 1), date(2023, 3, 31))
    assert period_window("Q3FY2024") == (date(2023, 10, 1), date(2023, 12, 31))
    assert period_window("Q4CY2022") == (date(2022, 10, 1), date(2022, 12, 31))


def test_fy_and_cy_of_the_same_year_are_not_the_same_period():
    # The whole reason the units axis exists.
    assert not same_period("FY2023", "CY2023")
    assert not same_period("FY2023", "CY2022")


def test_same_period_across_spellings():
    assert same_period("FY2023", "2022-23")
    assert same_period("FY23", "FY 2022-2023")
