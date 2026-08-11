"""Submission format and its validator.

This is one of the three surfaces an outside user touches, so every failure mode
is tested and every message names the offending input.

A submission is a single JSON file:

    {
      "model": "vendor/model-name",
      "model_version": "2026-01-31",
      "contact": "you@example.com",
      "open_weights": false,
      "notes": "optional; anything the leaderboard should carry",
      "predictions": [
        {"item_id": "...", "figures": {...}, "periods": {...},
         "steps": {...}, "final_value": 12.3, "final_unit": "percent"}
      ]
    }

Predictions must cover the test split exactly: every item, no extras. Partial
submissions are rejected rather than scored over what was supplied, because a
model that answers only the items it finds easy would otherwise post the
highest number on the board.
"""

from __future__ import annotations

import json
from pathlib import Path

from .scoring import Prediction
from .units import UnitError, family

REQUIRED_META = ("model", "model_version", "contact", "open_weights")
GOLD_FIELDS = ("tolerance", "reasoning_depth", "unit_trap", "value_as_printed")


class SubmissionError(ValueError):
    """Every message names the file and the offending item."""


def _fail(path, msg: str) -> None:
    raise SubmissionError(f"{path}: {msg}")


def validate(path: str | Path, expected_item_ids: set[str] | None = None) -> dict[str, Prediction]:
    """Validate a submission file. Returns the parsed predictions.

    `expected_item_ids` is the test split. Omit it only when you are checking
    the file's shape without the benchmark data present.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"{path} not found")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _fail(path, f"not valid JSON ({exc.msg} at line {exc.lineno}, column {exc.colno})")
    if not isinstance(doc, dict):
        _fail(path, f"top level must be a JSON object, got {type(doc).__name__}")

    missing = [k for k in REQUIRED_META if k not in doc]
    if missing:
        _fail(path, f"missing required field(s) {missing}; see docs/submission.md")
    if not isinstance(doc["open_weights"], bool):
        _fail(path, f"'open_weights' must be true or false, got {doc['open_weights']!r}")
    for key in ("model", "model_version", "contact"):
        if not isinstance(doc[key], str) or not doc[key].strip():
            _fail(path, f"'{key}' must be a non-empty string, got {doc[key]!r}")

    preds_raw = doc.get("predictions")
    if not isinstance(preds_raw, list) or not preds_raw:
        _fail(path, "'predictions' must be a non-empty list")

    preds: dict[str, Prediction] = {}
    for i, row in enumerate(preds_raw):
        where = f"predictions[{i}]"
        if not isinstance(row, dict):
            _fail(path, f"{where}: must be an object, got {type(row).__name__}")
        if "item_id" not in row:
            _fail(path, f"{where}: missing 'item_id'")
        leaked = [f for f in GOLD_FIELDS if f in row]
        if leaked:
            _fail(path, f"{where} ({row['item_id']}): contains gold-only field(s) {leaked}; "
                        "a submission carries predictions, not the answer key")
        try:
            pred = Prediction.from_dict(row)
        except (ValueError, KeyError) as exc:
            _fail(path, f"{where}: {exc}")
        if pred.item_id in preds:
            _fail(path, f"{where}: duplicate prediction for item {pred.item_id!r}")
        if pred.final_value is None or not pred.final_unit:
            _fail(path, f"{where} ({pred.item_id}): final_value and final_unit are required")
        for unit_owner, unit in [("final_unit", pred.final_unit)] + \
                                [(f"figures[{k}]", v[1]) for k, v in pred.figures.items()] + \
                                [(f"steps[{k}]", v[1]) for k, v in pred.steps.items()]:
            try:
                family(unit)
            except UnitError as exc:
                _fail(path, f"{where} ({pred.item_id}) {unit_owner}: {exc}")
        preds[pred.item_id] = pred

    if expected_item_ids is not None:
        missing_ids = sorted(expected_item_ids - preds.keys())
        extra_ids = sorted(preds.keys() - expected_item_ids)
        if missing_ids:
            _fail(path, f"{len(missing_ids)} test item(s) have no prediction, e.g. {missing_ids[:5]}. "  # not-a-sample: truncating an error message
                        "Partial submissions are not scored: answering only the easy items would "
                        "top the board.")
        if extra_ids:
            _fail(path, f"prediction(s) for unknown item(s) {extra_ids[:5]}; the test split has "  # not-a-sample: truncating an error message
                        f"{len(expected_item_ids)} items")
    return preds
