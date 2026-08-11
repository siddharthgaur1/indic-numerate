#!/usr/bin/env python
"""Assign documents to train/test, stratified by sector and fiscal year.

Writes data/splits/train_ids.json and data/splits/test_ids.json (document ids)
and prints the per-stratum counts, which are the numbers the README quotes.

    python scripts/build_splits.py
    python scripts/build_splits.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from indic_numerate.corpus import load_corpus  # noqa: E402
from indic_numerate.rng import SEED  # noqa: E402
from indic_numerate.splits import TEST_FRACTION, assign_splits, stratum_counts  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "data" / "corpus.jsonl"
SPLIT_DIR = ROOT / "data" / "splits"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--test-fraction", type=float, default=TEST_FRACTION)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    docs = load_corpus(CORPUS)
    splits = assign_splits(docs, args.test_fraction)
    train = sorted(d for d, s in splits.items() if s == "train")
    test = sorted(d for d, s in splits.items() if s == "test")

    print(f"seed={SEED} test_fraction={args.test_fraction}")
    print(f"{len(docs)} documents -> {len(train)} train / {len(test)} test")
    for key, counts in stratum_counts(docs, splits).items():
        print(f"\n{key}:")
        for cell, n in counts.items():
            print(f"  {cell:40s} {n}")

    if args.dry_run:
        print("\n--dry-run: nothing written")
        return 0

    SPLIT_DIR.mkdir(parents=True, exist_ok=True)
    (SPLIT_DIR / "train_ids.json").write_text(json.dumps(train, indent=1), encoding="utf-8")
    (SPLIT_DIR / "test_ids.json").write_text(json.dumps(test, indent=1), encoding="utf-8")
    print(f"\nwrote {SPLIT_DIR}/train_ids.json and test_ids.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
