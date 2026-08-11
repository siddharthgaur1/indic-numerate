"""Seeded, stratified splitting -- and the discipline that keeps it intact.

Two rules this module exists to enforce:

1. Splits are assigned at the DOCUMENT level, never the item level. Two items
   from the same annual report share pages, tables and phrasing; splitting by
   item leaks the test set into training.

2. Every stratum is split independently, so the proportions survive into both
   halves. Stratification that only holds over the whole population is worth
   nothing to the person who takes the first 50 rows -- which is why the split
   is applied within (sector, fiscal_year) cells and why every consumer that
   takes a prefix must go through `rng.take`.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Sequence, TypeVar

from .corpus import Document
from .rng import shuffled

T = TypeVar("T")

TEST_FRACTION = 0.30
STRATA = ("sector", "fiscal_year")


def stratum_of(doc: Document) -> tuple[str, ...]:
    return tuple(str(getattr(doc, k)) for k in STRATA)


def assign_splits(docs: Sequence[Document], test_fraction: float = TEST_FRACTION) -> dict[str, str]:
    """doc_id -> 'train' | 'test', stratified by sector and fiscal year.

    Within each stratum the documents are shuffled with the shared seed and the
    first ceil(n * test_fraction) go to test. A stratum of one document goes to
    train: a single-document stratum in test would make that cell's score a
    coin flip reported to three decimal places.
    """
    if not 0 < test_fraction < 1:
        raise ValueError(f"test_fraction must be strictly between 0 and 1, got {test_fraction}")
    if not docs:
        raise ValueError("cannot split an empty corpus")

    cells: dict[tuple[str, ...], list[Document]] = defaultdict(list)
    for doc in docs:
        cells[stratum_of(doc)].append(doc)

    out: dict[str, str] = {}
    for key, members in sorted(cells.items()):
        # Salt with the stratum key so cells are shuffled independently and
        # adding a new sector cannot reshuffle the existing ones.
        ordered = shuffled(sorted(members, key=lambda d: d.doc_id), salt="split:" + "|".join(key))
        n_test = 0 if len(ordered) < 2 else max(1, round(len(ordered) * test_fraction))
        for i, doc in enumerate(ordered):
            out[doc.doc_id] = "test" if i < n_test else "train"
    return out


def stratum_counts(docs: Sequence[Document], splits: dict[str, str]) -> dict[str, dict[str, int]]:
    """Per-split counts for each stratum key. What the tests assert on, and what
    the README's corpus table is generated from."""
    counts: dict[str, dict[str, int]] = {k: defaultdict(int) for k in STRATA}
    for doc in docs:
        split = splits.get(doc.doc_id, "unassigned")
        for k in STRATA:
            counts[k][f"{getattr(doc, k)}/{split}"] += 1
    return {k: dict(sorted(v.items())) for k, v in counts.items()}
