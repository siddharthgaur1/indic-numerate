"""Runner, adapters, cache, and the submission validator.

The validator is the third surface an outside user touches, so every raise site
here is asserted on and every message must name the offending prediction.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from fixtures import VALID, item
from indic_numerate.adapters import EchoAdapter, build
from indic_numerate.runner import (
    Cache, build_context, build_prompt, cache_key, extract_json, predict, run,
)
from indic_numerate.schema import Item
from indic_numerate.scoring import item_correct, score_item
from indic_numerate.submission import SubmissionError, validate

GOLD = Item.model_validate(VALID)

GOOD_RESPONSE = json.dumps(
    {
        "figures": {"f1": {"value": 1200, "unit": "crore"}, "f2": {"value": 1000, "unit": "crore"}},
        "periods": {"f1": "FY2023", "f2": "FY2022"},
        "steps": {"s1": {"value": 200, "unit": "crore"}, "s2": {"value": 20, "unit": "percent"}},
        "final_value": 20,
        "final_unit": "percent",
    }
)


# --- adapters --------------------------------------------------------------


def test_build_known_adapters():
    assert build("ollama:llama3.2").version == "llama3.2"
    assert build("echo").name == "echo"


def test_build_rejects_unknown_provider():
    with pytest.raises(ValueError, match="unknown adapter 'gpt5000'"):
        build("gpt5000:turbo")


def test_api_adapters_refuse_to_call_without_a_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    pytest.importorskip("anthropic")
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        build("anthropic").generate("hi")


def test_ollama_reports_an_unreachable_host():
    adapter = build("ollama:llama3.2")
    adapter.host = "http://localhost:1"  # nothing listens here
    with pytest.raises(RuntimeError, match="could not reach Ollama"):
        adapter.generate("hi")


# --- prompt and parsing ----------------------------------------------------


def test_prompt_states_the_expected_shape():
    p = build_prompt(GOLD)
    assert "f1..f2" in p and "s1..s2" in p and GOLD.question in p


def test_prompt_does_not_leak_gold_values():
    """The prompt states the SHAPE of the chain, never any of its values."""
    p = build_prompt(GOLD)
    for fig in GOLD.figures:
        assert str(fig.value_as_printed) not in p
        assert fig.label not in p
    for step in GOLD.steps:
        assert step.description not in p


def test_context_none_is_empty():
    assert build_context(GOLD, "none") == ""


def test_context_rejects_an_unknown_mode():
    with pytest.raises(ValueError, match="unknown context mode 'everything'"):
        build_context(GOLD, "everything")


def test_context_requires_the_document_rather_than_inventing_one(tmp_path):
    with pytest.raises(FileNotFoundError, match="fetch_reports.py"):
        build_context(GOLD, "anchored", pdf_dir=tmp_path)


def test_prompt_carries_the_context_when_given():
    p = build_prompt(GOLD, "Document extract (1 pages):\n--- page 84 ---\nRevenue 1200")
    assert "--- page 84 ---" in p and GOLD.question in p


def test_extract_json_from_fenced_prose():
    assert extract_json('Sure!\n```json\n{"a": 1}\n```\nHope that helps') == {"a": 1}


def test_extract_json_names_the_response_when_there_is_none():
    with pytest.raises(ValueError, match="no JSON object"):
        extract_json("I cannot answer that.")


# --- predict / cache -------------------------------------------------------


def test_predict_scores_a_good_response():
    pred, note = predict(GOLD, EchoAdapter(GOOD_RESPONSE), cache=None, context_mode="none")
    assert note == "called" and item_correct(score_item(GOLD, pred))


def test_unparseable_response_scores_zero_rather_than_raising():
    pred, note = predict(GOLD, EchoAdapter("I don't know."), cache=None, context_mode="none")
    assert "unparseable" in note
    assert not item_correct(score_item(GOLD, pred))


def test_malformed_prediction_scores_zero_rather_than_raising():
    bad = json.dumps({"figures": {"f1": "1200 crore"}, "final_value": 20, "final_unit": "percent"})
    pred, note = predict(GOLD, EchoAdapter(bad), cache=None, context_mode="none")
    assert "malformed" in note and pred.final_value is None


class CountingAdapter(EchoAdapter):
    def __init__(self, response):
        super().__init__(response, name="counting")
        self.calls = 0

    def generate(self, prompt):
        self.calls += 1
        return self.response


def test_cache_prevents_a_second_call(tmp_path):
    adapter = CountingAdapter(GOOD_RESPONSE)
    cache = Cache(tmp_path)
    predict(GOLD, adapter, cache, context_mode="none")
    _, note = predict(GOLD, adapter, cache, context_mode="none")
    assert adapter.calls == 1 and note == "cached"


def test_cache_key_changes_with_model_version(tmp_path):
    a, b = EchoAdapter("x"), EchoAdapter("x")
    b.version = "echo-2"
    prompt = build_prompt(GOLD)
    assert cache_key(GOLD, a, prompt) != cache_key(GOLD, b, prompt)


def test_cache_key_changes_with_the_prompt():
    a = EchoAdapter("x")
    assert cache_key(GOLD, a, "one") != cache_key(GOLD, a, "two")


def test_cache_key_is_stable_for_the_same_inputs():
    a = EchoAdapter("x")
    assert cache_key(GOLD, a, "one") == cache_key(GOLD, a, "one")


def test_run_returns_one_prediction_per_item(tmp_path, capsys):
    items = [GOLD, Item.model_validate(item(item_id="fixture-002"))]
    preds = run(items, EchoAdapter(GOOD_RESPONSE), tmp_path, context_mode="none")
    assert set(preds) == {"fixture-001", "fixture-002"}


# --- submission validator --------------------------------------------------


def submission(tmp_path, **over) -> str:
    doc = {
        "model": "vendor/model-x",
        "model_version": "2026-02-01",
        "contact": "someone@example.com",
        "open_weights": False,
        "predictions": [
            {
                "item_id": "fixture-001",
                "figures": {"f1": {"value": 1200, "unit": "crore"}, "f2": {"value": 1000, "unit": "crore"}},
                "steps": {"s1": {"value": 200, "unit": "crore"}, "s2": {"value": 20, "unit": "percent"}},
                "final_value": 20,
                "final_unit": "percent",
            }
        ],
    }
    doc.update(over)
    p = tmp_path / "sub.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return str(p)


def test_valid_submission(tmp_path):
    preds = validate(submission(tmp_path), {"fixture-001"})
    assert preds["fixture-001"].final_value == Decimal("20")


def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError, match="nope.json"):
        validate(tmp_path / "nope.json")


def test_not_json(tmp_path):
    p = tmp_path / "sub.json"
    p.write_text("{oops", encoding="utf-8")
    with pytest.raises(SubmissionError, match="not valid JSON"):
        validate(p)


def test_top_level_must_be_an_object(tmp_path):
    p = tmp_path / "sub.json"
    p.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(SubmissionError, match="must be a JSON object, got list"):
        validate(p)


def test_missing_metadata_names_the_fields(tmp_path):
    p = tmp_path / "sub.json"
    p.write_text(json.dumps({"model": "x", "predictions": []}), encoding="utf-8")
    with pytest.raises(SubmissionError, match=r"missing required field\(s\).*model_version"):
        validate(p)


def test_open_weights_must_be_boolean(tmp_path):
    with pytest.raises(SubmissionError, match="'open_weights' must be true or false, got 'no'"):
        validate(submission(tmp_path, open_weights="no"))


def test_blank_contact_rejected(tmp_path):
    with pytest.raises(SubmissionError, match="'contact' must be a non-empty string"):
        validate(submission(tmp_path, contact="  "))


def test_empty_predictions_rejected(tmp_path):
    with pytest.raises(SubmissionError, match="non-empty list"):
        validate(submission(tmp_path, predictions=[]))


def test_prediction_must_be_an_object(tmp_path):
    with pytest.raises(SubmissionError, match=r"predictions\[0\]: must be an object, got str"):
        validate(submission(tmp_path, predictions=["fixture-001"]))


def test_prediction_missing_item_id(tmp_path):
    with pytest.raises(SubmissionError, match="missing 'item_id'"):
        validate(submission(tmp_path, predictions=[{"final_value": 20, "final_unit": "percent"}]))


def test_gold_fields_are_rejected(tmp_path):
    row = {"item_id": "fixture-001", "final_value": 20, "final_unit": "percent", "unit_trap": True}
    with pytest.raises(SubmissionError, match="gold-only field"):
        validate(submission(tmp_path, predictions=[row]))


def test_duplicate_prediction(tmp_path):
    row = {"item_id": "fixture-001", "final_value": 20, "final_unit": "percent"}
    with pytest.raises(SubmissionError, match="duplicate prediction"):
        validate(submission(tmp_path, predictions=[row, dict(row)]))


def test_final_answer_is_required(tmp_path):
    with pytest.raises(SubmissionError, match="final_value and final_unit are required"):
        validate(submission(tmp_path, predictions=[{"item_id": "fixture-001", "final_unit": "percent"}]))


def test_unknown_unit_names_the_item_and_the_field(tmp_path):
    row = {"item_id": "fixture-001", "final_value": 20, "final_unit": "bananas"}
    with pytest.raises(SubmissionError, match=r"fixture-001\) final_unit: unknown unit 'bananas'"):
        validate(submission(tmp_path, predictions=[row]))


def test_unknown_unit_in_a_figure(tmp_path):
    row = {
        "item_id": "fixture-001",
        "figures": {"f1": {"value": 1, "unit": "bananas"}},
        "final_value": 20,
        "final_unit": "percent",
    }
    with pytest.raises(SubmissionError, match=r"figures\[f1\]: unknown unit"):
        validate(submission(tmp_path, predictions=[row]))


def test_partial_submission_is_rejected(tmp_path):
    with pytest.raises(SubmissionError, match="have no prediction"):
        validate(submission(tmp_path), {"fixture-001", "fixture-002", "fixture-003"})


def test_predictions_for_unknown_items_are_rejected(tmp_path):
    rows = [
        {"item_id": "fixture-001", "final_value": 20, "final_unit": "percent"},
        {"item_id": "fixture-999", "final_value": 1, "final_unit": "percent"},
    ]
    with pytest.raises(SubmissionError, match="unknown item"):
        validate(submission(tmp_path, predictions=rows), {"fixture-001"})


def test_shape_only_validation_skips_coverage(tmp_path):
    assert validate(submission(tmp_path), None)
