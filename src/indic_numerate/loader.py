"""JSONL loader. Fails loudly, never substitutes.

There is no synthetic fallback anywhere in this repo. A missing corpus file
raises with instructions for obtaining the real one; it does not generate a
stand-in. A benchmark that can manufacture its own inputs cannot be falsified.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from pydantic import ValidationError

from .schema import Item


class ItemLoadError(ValueError):
    """Raised for any malformed row. Message always names file:line."""


def _fmt(exc: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(p) for p in e['loc']) or '<item>'}: {e['msg']}"
        for e in exc.errors()
    )


def iter_items(path: str | Path) -> Iterator[Item]:
    """Yield validated Items from a JSONL file, in file order.

    Callers that slice this must reshuffle first -- see indic_numerate.rng.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} not found. indic-numerate ships no generated data: fetch the real "
            "items with `git lfs pull` / from the HuggingFace mirror, or author them with "
            "`python scripts/write_items.py`. Nothing here will synthesise a substitute."
        )
    seen: set[str] = set()
    empty = True
    with path.open(encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            if not raw.strip():
                continue
            empty = False
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ItemLoadError(f"{path}:{lineno}: not valid JSON ({exc.msg})") from exc
            if not isinstance(row, dict):
                raise ItemLoadError(f"{path}:{lineno}: expected a JSON object, got {type(row).__name__}")
            try:
                item = Item.model_validate(row)
            except ValidationError as exc:
                raise ItemLoadError(
                    f"{path}:{lineno}: item {row.get('item_id', '<no item_id>')!r} is invalid -- {_fmt(exc)}"
                ) from exc
            if item.item_id in seen:
                raise ItemLoadError(f"{path}:{lineno}: duplicate item_id {item.item_id!r}")
            seen.add(item.item_id)
            yield item
    if empty:
        raise ItemLoadError(f"{path}: contains no items. An empty split silently scores 100%.")


def load_items(path: str | Path, split: str | None = None) -> list[Item]:
    """Load and validate all items, optionally restricted to one split."""
    items = list(iter_items(path))
    if split is None:
        return items
    if split not in ("train", "test"):
        raise ValueError(f"unknown split {split!r}; expected 'train' or 'test'")
    kept = [i for i in items if i.split == split]
    if not kept:
        raise ItemLoadError(
            f"{path}: no items assigned to split {split!r} (of {len(items)} loaded). "
            "Run scripts/build_splits.py before evaluating."
        )
    return kept
