"""The seed lives here and nowhere else.

Every sampling path in this repo imports SEED from this module. Constraint:
any code that takes a prefix, a --limit, or an early stop from an ordered
collection must call `shuffled()` first. An ordered set sliced without
reshuffling is a biased sample that looks like a sample, and it has produced
published claims that were wrong (see README, "Sampling frame").

tests/test_sampling_frame.py greps the repo and fails if a slice appears
without a preceding shuffle.
"""

from __future__ import annotations

import random
from typing import Iterable, Sequence, TypeVar

SEED = 20240917

T = TypeVar("T")


def rng(salt: str = "") -> random.Random:
    """A fresh, independently reproducible RNG. `salt` separates streams
    (splits vs authoring order) without introducing a second seed."""
    return random.Random(f"{SEED}:{salt}")


def shuffled(items: Iterable[T], salt: str = "") -> list[T]:
    """Seeded shuffle. Call this before ANY prefix, limit or early stop."""
    out = list(items)
    rng(salt).shuffle(out)
    return out


def take(items: Sequence[T], n: int | None, salt: str = "") -> list[T]:
    """Seeded shuffle then take n. The only sanctioned way to take a subset."""
    out = shuffled(items, salt)
    return out if n is None else out[:n]
