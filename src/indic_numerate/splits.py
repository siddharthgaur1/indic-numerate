"""Seeded, stratified splitting -- and the discipline that keeps it intact.

Two rules this module exists to enforce:

1. Splits are assigned at the COMPANY level, never per item and never per
   document. This started as a document-level split, which was wrong and the
   oracle ceiling caught it: a company's FY2025 annual report prints its FY2024
   figures as the comparative column, so putting `infy-fy2024` in train and
   `infy-fy2025` in test leaks the test answers into the training set literally,
   not just by correlation. The oracle's train-prior attack scored +0.135 above
   chance off exactly that pair. Every document of one company now lands on the
   same side.

2. Every stratum is split independently, so the proportions survive into both
   halves. Stratification that only holds over the whole population is worth
   nothing to the person who takes the first 50 rows -- which is why the split is
   applied within sector cells and why every consumer that takes a prefix must go
   through `rng.take`.

Fiscal year is no longer a stratification key. It cannot be: a company has
documents in both years and the whole company moves together. Both years appear
on both sides as a consequence of splitting companies, and
`stratum_counts` still reports the fiscal-year breakdown so the balance stays
visible.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Sequence, TypeVar

from .corpus import Document
from .rng import shuffled

T = TypeVar("T")

TEST_FRACTION = 0.30
STRATA = ("sector", "fiscal_year")   # reported on; only `sector` is split within
SPLIT_STRATUM = "sector"


def stratum_of(doc: Document) -> tuple[str, ...]:
    return (str(getattr(doc, SPLIT_STRATUM)),)


def company_key(doc: Document) -> str:
    """The unit of splitting. Normalised so 'Infosys Ltd.' and 'Infosys Limited'
    cannot end up on opposite sides of the split."""
    name = doc.company.lower()
    for suffix in (" limited", " ltd.", " ltd", " corporation", " corp.", " corp", " (india)"):
        name = name.replace(suffix, "")
    return " ".join(name.split())


def assign_splits(docs: Sequence[Document], test_fraction: float = TEST_FRACTION) -> dict[str, str]:
    """doc_id -> 'train' | 'test'. Whole companies move together, within sector.

    A company's later report contains its earlier report's figures as
    comparatives, so splitting its documents apart puts test answers in the
    training set. Companies are grouped first, then each sector's companies are
    shuffled with the shared seed and the first round(n * test_fraction) go to
    test. A sector with one company sends it to train: a single-company sector in
    test would make that cell's score a coin flip reported to three decimals.
    """
    if not 0 < test_fraction < 1:
        raise ValueError(f"test_fraction must be strictly between 0 and 1, got {test_fraction}")
    if not docs:
        raise ValueError("cannot split an empty corpus")

    # sector -> company -> documents
    cells: dict[tuple[str, ...], dict[str, list[Document]]] = defaultdict(lambda: defaultdict(list))
    for doc in docs:
        cells[stratum_of(doc)][company_key(doc)].append(doc)

    out: dict[str, str] = {}
    for key, companies in sorted(cells.items()):
        # Salt with the stratum key so cells are shuffled independently and
        # adding a new sector cannot reshuffle the existing ones.
        ordered = shuffled(sorted(companies), salt="split:" + "|".join(key))
        n_test = 0 if len(ordered) < 2 else max(1, round(len(ordered) * test_fraction))
        for i, company in enumerate(ordered):
            split = "test" if i < n_test else "train"
            for doc in companies[company]:
                out[doc.doc_id] = split
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
