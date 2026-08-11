import pytest
from pydantic import ValidationError

from fixtures import VALID, item
from indic_numerate.schema import Item, period_basis


def err(**overrides):
    with pytest.raises(ValidationError) as e:
        Item.model_validate(item(**overrides))
    return str(e.value)


def test_valid_fixture_parses():
    assert Item.model_validate(VALID).reasoning_depth == 2


def test_period_basis():
    assert period_basis("FY2023") == "FY"
    assert period_basis("CY2022") == "CY"
    assert period_basis("Q3FY2024") == "FY"
    with pytest.raises(ValueError, match="FY2023"):
        period_basis("2023-24")


def test_malformed_period_named_in_message():
    assert "'FY23'" in err(figures=[{**VALID["figures"][0], "period": "FY23"}, VALID["figures"][1]])


def test_restated_without_note():
    msg = err(figures=[{**VALID["figures"][0], "restated": True}, VALID["figures"][1]])
    assert "restatement_note" in msg and "f1" in msg


def test_duplicate_fig_id():
    assert "duplicate fig_id" in err(figures=[VALID["figures"][0], {**VALID["figures"][1], "fig_id": "f1"}])


def test_step_ids_must_be_sequential():
    steps = [{**VALID["steps"][0], "step_id": "s2"}, {**VALID["steps"][1], "step_id": "s3", "inputs": ["s2", "f2"]}]
    assert "s1..s2" in err(steps=steps)


def test_unknown_step_input():
    steps = [{**VALID["steps"][0], "inputs": ["f1", "f9"]}, VALID["steps"][1]]
    assert "f9" in err(steps=steps)


def test_step_cannot_reference_later_step():
    steps = [{**VALID["steps"][0], "inputs": ["f1", "s2"]}, VALID["steps"][1]]
    assert "s2" in err(steps=steps)


def test_orphan_figure_rejected():
    figs = VALID["figures"] + [{"fig_id": "f3", "label": "Unused decoy", "value_as_printed": "5",
                                "unit_as_printed": "crore", "page": 9, "period": "FY2023"}]
    assert "never used by a step" in err(figures=figs)


def test_depth_must_equal_step_count():
    assert "reasoning_depth=3" in err(reasoning_depth=3)


def test_final_must_match_last_step():
    assert "cancelling errors" in err(final_value="21")


def test_final_unit_must_match_last_step():
    assert "does not match" in err(final_unit="ratio")


def test_unit_trap_must_be_derived_not_asserted():
    assert "unit_trap=True" in err(unit_trap=True)


def test_mixed_printed_units_forces_trap_flag():
    figs = [{**VALID["figures"][0], "unit_as_printed": "lakh", "value_as_printed": "120000"}, VALID["figures"][1]]
    assert "imply True" in err(figures=figs)


def test_mixed_fy_cy_basis_forces_trap_flag():
    figs = [VALID["figures"][0], {**VALID["figures"][1], "period": "CY2022"}]
    assert "imply True" in err(figures=figs)


def test_convert_step_forces_trap_flag():
    steps = [{**VALID["steps"][0], "operation": "convert"}, VALID["steps"][1]]
    assert "imply True" in err(steps=steps)


def test_dimensionless_answer_requires_absolute_tolerance():
    assert "dimensionless" in err(tolerance={"mode": "relative", "value": "0.01"})


def test_monetary_answer_requires_relative_tolerance():
    steps = [VALID["steps"][0], {**VALID["steps"][1], "operation": "add", "value": "1400", "unit": "crore"}]
    msg = err(steps=steps, final_value="1400", final_unit="crore")
    assert "monetary" in msg


def test_answer_in_question_is_circular():
    steps = [VALID["steps"][0], {**VALID["steps"][1], "operation": "add", "value": "1400", "unit": "crore"}]
    q = "Given segment revenues, what is the combined total, which the summary states as 1,400 crore?"
    msg = err(steps=steps, final_value="1400", final_unit="crore",
              tolerance={"mode": "relative", "value": "0.005"}, question=q)
    assert "circular" in msg


def test_short_answers_escape_the_circularity_tripwire():
    """Documents the known ceiling: <3 significant digits is not checked."""
    Item.model_validate(item(question="What was the percentage growth, roughly 20 percent, over the year?"))


def test_extra_fields_rejected():
    assert "answer_hint" in err(answer_hint="20 percent")
