"""The numbers the README quotes, computed from the data, in one place.

Caveats are load-bearing: a documented number that drifts leaves the README
lying, and a stale README is a regression like any other. So the counts live in
a generated block between markers, `scripts/update_readme.py` regenerates it,
and `tests/test_readme.py` fails if the file on disk disagrees with the data.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from .rng import SEED

BEGIN = "<!-- BEGIN GENERATED COUNTS -->"
END = "<!-- END GENERATED COUNTS -->"


def current_counts(root: Path) -> dict:
    """Counts from data/. Absent files mean zero, never an estimate."""
    from .corpus import load_corpus
    from .loader import load_items

    out = {"seed": SEED, "documents": 0, "items": 0, "train_items": 0, "test_items": 0,
           "unit_trap_items": 0, "sectors": 0, "fiscal_years": 0, "depths": {}}
    try:
        docs = load_corpus(root / "data" / "corpus.jsonl")
    except (FileNotFoundError, ValueError):
        docs = []
    out["documents"] = len(docs)
    out["sectors"] = len({d.sector for d in docs})
    out["fiscal_years"] = len({d.fiscal_year for d in docs})
    try:
        items = load_items(root / "data" / "items.jsonl")
    except (FileNotFoundError, ValueError):
        items = []
    out["items"] = len(items)
    out["train_items"] = sum(i.split == "train" for i in items)
    out["test_items"] = sum(i.split == "test" for i in items)
    out["unit_trap_items"] = sum(i.unit_trap for i in items)
    out["depths"] = dict(sorted(Counter(i.reasoning_depth for i in items).items()))
    return out


def render_block(counts: dict) -> str:
    depth = ", ".join(f"{k}-step: {v}" for k, v in counts["depths"].items()) or "none yet"
    lines = [
        BEGIN,
        "| | |",
        "|---|---|",
        f"| documents | {counts['documents']} |",
        f"| items | {counts['items']} ({counts['train_items']} train / {counts['test_items']} test) |",
        f"| unit-trap items | {counts['unit_trap_items']} |",
        f"| reasoning depth | {depth} |",
        f"| sectors / fiscal years | {counts['sectors']} / {counts['fiscal_years']} |",
        f"| seed | {counts['seed']} |",
        END,
    ]
    return "\n".join(lines)


def replace_block(text: str, block: str) -> str:
    if BEGIN not in text or END not in text:
        raise ValueError(f"README is missing the {BEGIN} / {END} markers")
    head, rest = text.split(BEGIN, 1)
    _, tail = rest.split(END, 1)
    return head + block + tail
