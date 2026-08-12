"""Drafts are machine-authored, so the tests on them are stricter, not looser.

These check the properties a reviewer would otherwise have to hold in their head:
that drafts never masquerade as benchmark items, that the drafted chains are
arithmetically consistent with the figures they cite, and that the promotion path
requires a human.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

import promote_items
from indic_numerate.loader import load_items
from indic_numerate.units import convert

ROOT = Path(__file__).resolve().parents[1]
DRAFTS = ROOT / "data" / "items_draft.jsonl"
ITEMS = ROOT / "data" / "items.jsonl"
DROPS = ROOT / "data" / "drops.jsonl"

pytestmark = pytest.mark.skipif(not DRAFTS.is_file(), reason="no drafts yet")


def drafts():
    return load_items(DRAFTS)


def test_drafts_are_not_in_the_benchmark_file():
    """The whole point of the draft file: unreviewed gold must not be loadable as
    benchmark gold. Promotion is a human act, recorded in data/promotions.jsonl."""
    if not ITEMS.is_file():
        return
    promoted = {i.item_id for i in load_items(ITEMS)}
    for item in drafts():
        assert item.item_id not in promoted, f"{item.item_id} appears verbatim in items.jsonl"


def test_every_promoted_item_has_a_promotion_record():
    """Provenance chain: an item that came from a draft must be traceable to the
    promotion that put it in the benchmark, and to whoever signed it."""
    if not ITEMS.is_file():
        return
    log_path = ROOT / "data" / "promotions.jsonl"
    assert log_path.is_file(), "items.jsonl exists but no promotions were recorded"
    log = {json.loads(l)["item_id"]: json.loads(l) for l in log_path.read_text(encoding="utf-8").splitlines() if l.strip()}
    draft_lineage = {promote_items.promoted_id(i.item_id) for i in drafts()}
    for item in load_items(ITEMS):
        if item.item_id in draft_lineage:
            assert item.item_id in log, (
                f"{item.item_id} came from a draft but has no entry in promotions.jsonl"
            )
            assert log[item.item_id]["reviewed_by"].strip(), f"{item.item_id}: empty reviewer"
            assert log[item.item_id]["promoted_at"]


def test_promotion_records_point_at_items_that_exist():
    log_path = ROOT / "data" / "promotions.jsonl"
    if not (log_path.is_file() and ITEMS.is_file()):
        return
    present = {i.item_id for i in load_items(ITEMS)}
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            assert row["item_id"] in present, (
                f"promotions.jsonl claims {row['item_id']} was promoted, but it is not in items.jsonl"
            )


def test_unreviewed_promotions_are_not_dressed_up_as_reviewed():
    """If a promotion was not a page-level human review, the record must say so
    rather than carrying a name that implies one."""
    log_path = ROOT / "data" / "promotions.jsonl"
    if not log_path.is_file():
        return
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        reviewer = json.loads(line)["reviewed_by"].lower()
        if "not page-level human reviewed" in reviewer:
            assert "have not been page-level human" in readme, (
                "items were promoted without human review, so the README must say so"
            )


def test_every_draft_id_is_marked_as_a_draft():
    for item in drafts():
        assert "-d0" in item.item_id, f"{item.item_id} is not identifiable as a draft"


def test_drafts_span_depths_and_traps():
    items = drafts()
    assert len({i.reasoning_depth for i in items}) >= 2
    assert any(i.unit_trap for i in items) and any(not i.unit_trap for i in items)
    assert {i.split for i in items} == {"train", "test"}


@pytest.mark.parametrize("op", ["subtract", "divide", "percent_change", "convert"])
def test_arithmetic_of_every_drafted_chain(op):
    """Recompute each step from its inputs. A typo in a gold value fails here.

    This is the check that makes machine-drafted chains auditable: the schema
    proves the chain is well formed, this proves it is arithmetically true.
    """
    for item in drafts():
        values = {f.fig_id: (f.value_as_printed, f.unit_as_printed) for f in item.figures}
        for step in item.steps:
            if step.operation == op:
                got = _apply(step, values)
                if got is not None:
                    want = step.value
                    tol = abs(want) * Decimal("0.0001") + Decimal("0.0001")
                    assert abs(got - want) <= tol, (
                        f"{item.item_id}/{step.step_id}: {step.operation} of {step.inputs} gives "
                        f"{got}, item claims {want}"
                    )
            values[step.step_id] = (step.value, step.unit)


def _apply(step, values):
    """Recompute one step in its own declared unit, or None if not checkable."""
    try:
        ins = [values[i] for i in step.inputs]
    except KeyError:
        return None
    def as_unit(pair, unit):
        return convert(pair[0], pair[1], unit)

    if step.operation == "subtract" and len(ins) == 2:
        return as_unit(ins[0], step.unit) - as_unit(ins[1], step.unit)
    if step.operation == "divide" and len(ins) == 2:
        a, b = as_unit(ins[0], ins[0][1]), convert(ins[1][0], ins[1][1], ins[0][1])
        return a / b
    if step.operation == "percent_change" and len(ins) == 2:
        change, base = ins[0], ins[1]
        base_in_change_unit = convert(base[0], base[1], change[1])
        return change[0] / base_in_change_unit * 100
    if step.operation == "convert" and len(ins) == 1:
        return as_unit(ins[0], step.unit)
    return None


def test_final_answer_matches_the_recomputed_chain():
    for item in drafts():
        assert item.final_value == item.steps[-1].value
        assert item.final_unit == item.steps[-1].unit


def test_drops_are_logged_with_a_reason_and_a_rule():
    assert DROPS.is_file(), "dropped items must be logged, not silently discarded"
    rows = [json.loads(l) for l in DROPS.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert rows
    for r in rows:
        assert r["reason"] and r["rule"].startswith("docs/annotation-guidelines.md")
        assert r["doc_id"] and r["attempted"]


# --- promotion -------------------------------------------------------------


def test_promotion_strips_the_draft_marker():
    assert promote_items.promoted_id("infy-fy2024-d01") == "infy-fy2024-01"
    assert promote_items.promoted_id("already-01") == "already-01"


def test_promotion_requires_a_reviewer(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["promote_items.py", "infy-fy2024-d01"])
    with pytest.raises(SystemExit) as e:
        promote_items.main()
    assert "--reviewed-by is required" in str(e.value)


def test_promotion_rejects_unknown_ids(monkeypatch):
    monkeypatch.setattr("sys.argv", ["promote_items.py", "no-such-item-d01", "--reviewed-by", "X"])
    with pytest.raises(SystemExit, match="not in items_draft.jsonl"):
        promote_items.main()


def test_promotion_requires_some_target(monkeypatch):
    monkeypatch.setattr("sys.argv", ["promote_items.py", "--reviewed-by", "X"])
    with pytest.raises(SystemExit, match="name the item ids"):
        promote_items.main()
