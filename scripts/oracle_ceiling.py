#!/usr/bin/env python
"""Try to score well WITHOUT reading the documents. If this succeeds, stop.

A benchmark whose answers can be recovered from the question text and metadata
alone measures nothing about documents. This script runs three metadata-only
attacks against the test split and compares them to a permutation baseline
(answers drawn at random from the train answer pool, averaged over seeds):

  question-numbers  copy a number that appears in the question itself
  train-prior       always answer the train median for the item's (unit, depth)
  nearest-question  copy the answer of the most lexically similar train question

Exit status 1 if any attack beats the permutation baseline by more than
--threshold on the final axis. That result is not a curiosity: it means the
benchmark is broken and must not be published until the leaking items are gone.

    python scripts/oracle_ceiling.py
    python scripts/oracle_ceiling.py --threshold 0.05
"""

from __future__ import annotations

import argparse
import re
import statistics
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from indic_numerate.loader import load_items  # noqa: E402
from indic_numerate.rng import SEED, rng  # noqa: E402
from indic_numerate.schema import Item  # noqa: E402
from indic_numerate.scoring import Prediction, score_final  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ITEMS = ROOT / "data" / "items.jsonl"
NUMBER_RE = re.compile(r"-?\d[\d,]*\.?\d*")
WORD_RE = re.compile(r"[a-z]{3,}")


def numbers_in(text: str) -> list[Decimal]:
    out = []
    for m in NUMBER_RE.findall(text):
        try:
            out.append(Decimal(m.replace(",", "")))
        except InvalidOperation:
            pass
    return out


def score(items: list[Item], guess) -> float:
    """Fraction of items whose final answer the guesser gets inside tolerance."""
    hits = 0
    for item in items:
        value = guess(item)
        if value is None:
            continue
        pred = Prediction(item_id=item.item_id, final_value=Decimal(str(value)), final_unit=item.final_unit)
        hits += score_final(item, pred).score == 1.0
    return hits / len(items)


def attack_question_numbers(_train: list[Item]):
    """Best case for the attacker: try every number in the question, keep the
    one that scores. An honest item leaks none of them."""

    def guess(item: Item):
        for n in numbers_in(item.question):
            pred = Prediction(item_id=item.item_id, final_value=n, final_unit=item.final_unit)
            if score_final(item, pred).score == 1.0:
                return n
        return None

    return guess


def attack_train_prior(train: list[Item]):
    by_key: dict[tuple[str, int], list[Decimal]] = {}
    for t in train:
        by_key.setdefault((t.final_unit, t.reasoning_depth), []).append(t.final_value)
    overall = [t.final_value for t in train]

    def guess(item: Item):
        pool = by_key.get((item.final_unit, item.reasoning_depth)) or overall
        return statistics.median(pool) if pool else None

    return guess


def attack_nearest_question(train: list[Item]):
    bags = [(set(WORD_RE.findall(t.question.lower())), t) for t in train]

    def guess(item: Item):
        q = set(WORD_RE.findall(item.question.lower()))
        best, best_sim = None, 0.0
        for bag, t in bags:
            if t.final_unit != item.final_unit:
                continue
            sim = len(q & bag) / len(q | bag) if q | bag else 0.0
            if sim > best_sim:
                best, best_sim = t, sim
        return best.final_value if best else None

    return guess


def permutation_baseline(train: list[Item], test: list[Item], n_trials: int = 200) -> float:
    """Chance level: answer each test item with a random train answer of the
    same unit. This is what 'meaningfully above chance' is measured against."""
    pool_by_unit: dict[str, list[Decimal]] = {}
    for t in train:
        pool_by_unit.setdefault(t.final_unit, []).append(t.final_value)
    r = rng("oracle")
    trials = []
    for _ in range(n_trials):
        def guess(item: Item, r=r):
            pool = pool_by_unit.get(item.final_unit)
            return r.choice(pool) if pool else None

        trials.append(score(test, guess))
    return sum(trials) / len(trials)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--items", default=str(ITEMS))
    ap.add_argument("--threshold", type=float, default=0.05,
                    help="how far above chance counts as broken (default 0.05)")
    args = ap.parse_args()

    train = load_items(args.items, split="train")
    test = load_items(args.items, split="test")
    chance = permutation_baseline(train, test)

    print(f"seed={SEED}  train={len(train)}  test={len(test)}")
    print(f"permutation baseline (chance) : {chance:.3f}\n")

    attacks = {
        "question-numbers": attack_question_numbers,
        "train-prior": attack_train_prior,
        "nearest-question": attack_nearest_question,
    }
    worst = 0.0
    for name, build in attacks.items():
        s = score(test, build(train))
        delta = s - chance
        worst = max(worst, delta)
        flag = "  <-- LEAK" if delta > args.threshold else ""
        print(f"{name:18s}: {s:.3f}  ({delta:+.3f} vs chance){flag}")

    print()
    if worst > args.threshold:
        print(
            f"FAIL: a metadata-only attack beats chance by {worst:+.3f} (> {args.threshold}).\n"
            "The benchmark is circular as it stands. Find the leaking items, drop them, and\n"
            "do not publish results until this passes. See docs/annotation-guidelines.md #7.",
            file=sys.stderr,
        )
        return 1
    print(f"PASS: no metadata-only attack beats chance by more than {args.threshold}.")
    print("Quote this number in the README next to the headline scores.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
