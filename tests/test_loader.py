import json

import pytest

from fixtures import VALID, item
from indic_numerate import ItemLoadError, load_items
from indic_numerate.loader import iter_items


def write(tmp_path, *rows, name="items.jsonl"):
    p = tmp_path / name
    p.write_text("\n".join(r if isinstance(r, str) else json.dumps(r) for r in rows), encoding="utf-8")
    return p


def test_loads_valid_file(tmp_path):
    p = write(tmp_path, VALID, item(item_id="fixture-002"))
    assert [i.item_id for i in load_items(p)] == ["fixture-001", "fixture-002"]


def test_blank_lines_ignored(tmp_path):
    assert len(load_items(write(tmp_path, VALID, "", "  "))) == 1


def test_missing_file_names_path_and_refuses_to_synthesise(tmp_path):
    with pytest.raises(FileNotFoundError) as e:
        load_items(tmp_path / "nope.jsonl")
    msg = str(e.value)
    assert "nope.jsonl" in msg and "synthesise" in msg


def test_bad_json_names_line(tmp_path):
    with pytest.raises(ItemLoadError, match=r"items\.jsonl:2:"):
        load_items(write(tmp_path, VALID, "{not json"))


def test_non_object_row(tmp_path):
    with pytest.raises(ItemLoadError, match="expected a JSON object, got list"):
        load_items(write(tmp_path, VALID, [1, 2]))


def test_invalid_item_names_line_and_item_id(tmp_path):
    with pytest.raises(ItemLoadError) as e:
        load_items(write(tmp_path, item(item_id="bad-one", reasoning_depth=4)))
    msg = str(e.value)
    assert "items.jsonl:1" in msg and "'bad-one'" in msg and "reasoning_depth=4" in msg


def test_missing_item_id_placeholder(tmp_path):
    row = item()
    del row["item_id"]
    with pytest.raises(ItemLoadError, match="<no item_id>"):
        load_items(write(tmp_path, row))


def test_duplicate_item_id(tmp_path):
    with pytest.raises(ItemLoadError, match="duplicate item_id 'fixture-001'"):
        load_items(write(tmp_path, VALID, VALID))


def test_empty_file_rejected(tmp_path):
    with pytest.raises(ItemLoadError, match="scores 100%"):
        load_items(write(tmp_path, ""))


def test_unknown_split_name(tmp_path):
    with pytest.raises(ValueError, match="unknown split 'dev'"):
        load_items(write(tmp_path, VALID), split="dev")


def test_split_filter(tmp_path):
    p = write(tmp_path, VALID, item(item_id="fixture-002", split="test"))
    assert [i.item_id for i in load_items(p, split="test")] == ["fixture-002"]


def test_empty_split_rejected(tmp_path):
    with pytest.raises(ItemLoadError, match="no items assigned to split 'test'"):
        load_items(write(tmp_path, VALID), split="test")


def test_iter_items_is_lazy_and_still_validates(tmp_path):
    it = iter_items(write(tmp_path, VALID, item(item_id="fixture-001")))
    assert next(it).item_id == "fixture-001"
    with pytest.raises(ItemLoadError, match="duplicate"):
        next(it)
