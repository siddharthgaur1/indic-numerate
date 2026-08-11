"""Each axis is testable in isolation, on fixtures, with no model in the loop."""

from decimal import Decimal

import pytest

from fixtures import VALID, item
from indic_numerate.report import build_report
from indic_numerate.schema import Item
from indic_numerate.scoring import (
    Prediction,
    item_correct,
    score_final,
    score_intermediate,
    score_item,
    score_retrieval,
    score_units,
)

GOLD = Item.model_validate(VALID)


def perfect(**over) -> Prediction:
    p = Prediction(
        item_id="fixture-001",
        figures={"f1": (Decimal("1200"), "crore"), "f2": (Decimal("1000"), "crore")},
        steps={"s1": (Decimal("200"), "crore"), "s2": (Decimal("20"), "percent")},
        periods={"f1": "FY2023", "f2": "FY2022"},
        final_value=Decimal("20"),
        final_unit="percent",
    )
    for k, v in over.items():
        setattr(p, k, v)
    return p


# --- retrieval -------------------------------------------------------------


def test_retrieval_all_hit():
    assert score_retrieval(GOLD, perfect()).score == 1.0


def test_retrieval_is_blind_to_units():
    # Right digits, wrong unit: retrieval is fine, units is not.
    p = perfect(figures={"f1": (Decimal("1200"), "lakh"), "f2": (Decimal("1000"), "crore")})
    assert score_retrieval(GOLD, p).score == 1.0
    assert score_units(GOLD, p).score < 1.0


def test_retrieval_partial_and_names_the_miss():
    p = perfect(figures={"f1": (Decimal("1200"), "crore"), "f2": (Decimal("999"), "crore")})
    s = score_retrieval(GOLD, p)
    assert s.score == 0.5 and "f2" in s.detail and "999" in s.detail


def test_retrieval_missing_figure_scores_zero_not_skipped():
    s = score_retrieval(GOLD, perfect(figures={}))
    assert s.score == 0.0 and "nothing" in s.detail


def test_retrieval_trailing_zeros_are_equal():
    p = perfect(figures={"f1": (Decimal("1200.00"), "crore"), "f2": (Decimal("1000"), "crore")})
    assert score_retrieval(GOLD, p).score == 1.0


# --- units -----------------------------------------------------------------


def test_units_all_correct():
    assert score_units(GOLD, perfect()).score == 1.0


def test_units_equivalent_magnitude_accepted():
    # 120000 lakh IS 1200 crore, but the digits differ so retrieval misses it
    # and the units axis skips it rather than double-counting the same error.
    p = perfect(figures={"f1": (Decimal("120000"), "lakh"), "f2": (Decimal("1000"), "crore")})
    assert score_retrieval(GOLD, p).score == 0.5
    assert score_units(GOLD, p).score == 1.0


def test_units_wrong_final_unit_family():
    s = score_units(GOLD, perfect(final_unit="crore"))
    assert s.score < 1.0 and "final unit" in s.detail


def test_units_unknown_unit_is_a_failure_not_a_crash():
    p = perfect(figures={"f1": (Decimal("1200"), "furlongs"), "f2": (Decimal("1000"), "crore")})
    assert score_units(GOLD, p).score < 1.0


def test_period_only_scored_on_trap_items():
    # Non-trap item: not reporting periods costs nothing.
    assert score_units(GOLD, perfect(periods={})).score == 1.0


def test_fy_cy_confusion_is_caught_on_trap_items():
    trap = Item.model_validate(
        item(
            figures=[
                {**VALID["figures"][0], "period": "CY2022"},
                {**VALID["figures"][1], "period": "FY2022"},
            ],
            unit_trap=True,
        )
    )
    good = score_units(trap, perfect(periods={"f1": "CY2022", "f2": "FY2022"}))
    bad = score_units(trap, perfect(periods={"f1": "FY2022", "f2": "FY2022"}))
    assert good.score == 1.0 and bad.score < 1.0 and "f1" in bad.detail


def test_period_spelling_variants_accepted():
    trap = Item.model_validate(
        item(figures=[{**VALID["figures"][0], "period": "CY2022"}, VALID["figures"][1]], unit_trap=True)
    )
    assert score_units(trap, perfect(periods={"f1": "cy22", "f2": "2021-22"})).score == 1.0


def test_unparseable_period_is_a_failure_not_a_crash():
    trap = Item.model_validate(
        item(figures=[{**VALID["figures"][0], "period": "CY2022"}, VALID["figures"][1]], unit_trap=True)
    )
    assert score_units(trap, perfect(periods={"f1": "whenever", "f2": "FY2022"})).score < 1.0


# --- intermediate ----------------------------------------------------------


def test_intermediate_correct():
    assert score_intermediate(GOLD, perfect()).score == 1.0


def test_intermediate_excludes_the_final_step():
    # Depth 2 -> exactly one intermediate (s1). s2 is the final answer.
    assert score_intermediate(GOLD, perfect()).n == 1


def test_intermediate_accepts_an_equivalent_unit():
    p = perfect(steps={"s1": (Decimal("20000"), "lakh"), "s2": (Decimal("20"), "percent")})
    assert score_intermediate(GOLD, p).score == 1.0


def test_intermediate_wrong_value():
    p = perfect(steps={"s1": (Decimal("300"), "crore")})
    s = score_intermediate(GOLD, p)
    assert s.score == 0.0 and "s1" in s.detail


def test_intermediate_not_reported():
    s = score_intermediate(GOLD, perfect(steps={}))
    assert s.score == 0.0 and "not reported" in s.detail


# --- final -----------------------------------------------------------------


def test_final_correct():
    assert score_final(GOLD, perfect()).score == 1.0


def test_final_within_absolute_tolerance():
    assert score_final(GOLD, perfect(final_value=Decimal("20.04"))).score == 1.0
    assert score_final(GOLD, perfect(final_value=Decimal("20.06"))).score == 0.0


def test_final_accepts_ratio_for_percent():
    assert score_final(GOLD, perfect(final_value=Decimal("0.2"), final_unit="ratio")).score == 1.0


def test_final_rejects_wrong_family():
    s = score_final(GOLD, perfect(final_unit="crore"))
    assert s.score == 0.0 and "wrong family" in s.detail


def test_final_missing_answer():
    assert score_final(GOLD, perfect(final_value=None)).score == 0.0


def test_final_unknown_unit_does_not_crash():
    assert score_final(GOLD, perfect(final_unit="parsecs")).score == 0.0


def test_relative_tolerance_on_a_monetary_answer():
    big = Item.model_validate(
        item(
            steps=[VALID["steps"][0], {**VALID["steps"][1], "operation": "add", "value": "1400", "unit": "crore"}],
            final_value="1400",
            final_unit="crore",
            tolerance={"mode": "relative", "value": "0.005"},
        )
    )
    p = perfect(final_value=Decimal("1405"), final_unit="crore")
    assert score_final(big, p).score == 1.0
    assert score_final(big, perfect(final_value=Decimal("1450"), final_unit="crore")).score == 0.0


# --- item level ------------------------------------------------------------


def test_item_correct_requires_all_four_axes():
    assert item_correct(score_item(GOLD, perfect()))


def test_cancelling_errors_do_not_score_correct():
    """The whole point: right final answer, wrong chain."""
    p = perfect(steps={"s1": (Decimal("240"), "crore"), "s2": (Decimal("20"), "percent")})
    scores = score_item(GOLD, p)
    assert scores["final"].score == 1.0
    assert scores["intermediate"].score == 0.0
    assert not item_correct(scores)


def test_score_item_rejects_mismatched_prediction():
    with pytest.raises(ValueError, match="does not match"):
        score_item(GOLD, perfect(item_id="someone-elses-item"))


def test_prediction_from_dict_roundtrip():
    p = Prediction.from_dict(
        {
            "item_id": "fixture-001",
            "figures": {"f1": {"value": "1200", "unit": "crore"}, "f2": {"value": 1000, "unit": "crore"}},
            "steps": {"s1": {"value": 200, "unit": "crore"}, "s2": {"value": 20, "unit": "percent"}},
            "periods": {"f1": "FY2023", "f2": "FY2022"},
            "final_value": 20,
            "final_unit": "percent",
        }
    )
    assert item_correct(score_item(GOLD, p))


def test_prediction_from_dict_rejects_malformed_figure():
    with pytest.raises(ValueError, match="figures\\['f1'\\]"):
        Prediction.from_dict({"item_id": "x", "figures": {"f1": "1200 crore"}})


def test_prediction_from_dict_rejects_non_numeric_final():
    with pytest.raises(ValueError, match="not a number"):
        Prediction.from_dict({"item_id": "x", "final_value": "about twenty"})


# --- report ----------------------------------------------------------------


def test_report_surfaces_the_cancelling_error_gap():
    items = [GOLD, Item.model_validate(item(item_id="fixture-002"))]
    preds = {
        "fixture-001": perfect(),
        "fixture-002": Prediction(
            item_id="fixture-002",
            figures={"f1": (Decimal("1200"), "crore"), "f2": (Decimal("1000"), "crore")},
            steps={"s1": (Decimal("240"), "crore")},
            final_value=Decimal("20"),
            final_unit="percent",
        ),
    }
    r = build_report("fixture-model", items, preds).to_dict()
    assert r["final_only_correct"] == 1.0
    assert r["all_axes_correct"] == 0.5
    assert r["cancelling_error_gap"] == 0.5


def test_report_counts_missing_predictions_as_zero():
    r = build_report("silent-model", [GOLD], {}).to_dict()
    assert r["all_axes_correct"] == 0.0 and r["n_items"] == 1


def test_report_rejects_empty_item_list():
    with pytest.raises(ValueError, match="empty split scores 100%"):
        build_report("m", [], {})


def test_report_keeps_strata_and_subsets():
    items = [GOLD, Item.model_validate(item(item_id="fixture-002", sector="pharma"))]
    r = build_report("m", items, {}).to_dict()
    assert r["strata"]["sector"] == {"it_services": 1, "pharma": 1}
    assert r["strata"]["fiscal_year"] == {"FY2023": 2}
    assert r["unit_trap_subset"]["n"] == 0 and r["no_trap_subset"]["n"] == 2


def test_report_markdown_renders():
    md = build_report("m", [GOLD], {"fixture-001": perfect()}).to_markdown()
    assert "| retrieval | units | intermediate | final | all four |" in md
