"""Aggregation. Per-axis, per-reasoning-depth, and the unit-trap subset.

The unit-trap subset is reported separately and never folded into the headline:
it is a different population, and averaging it in would let a model that avoids
trap items look like one that handles them.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field

from .scoring import AXES, AxisScore, Prediction, item_correct, score_item
from .schema import Item


def _mean(pairs: list[tuple[float, int]]) -> float:
    """Micro-average: weight each item by its number of checks on that axis.

    Macro-averaging would let a 1-figure item and a 4-figure item count equally
    on retrieval, which quietly rewards short items.
    """
    num = sum(s * n for s, n in pairs)
    den = sum(n for _, n in pairs)
    return round(num / den, 4) if den else float("nan")


@dataclass
class Report:
    model: str
    n_items: int
    axes: dict[str, float]
    all_axes_correct: float
    by_depth: dict[int, dict[str, float]] = field(default_factory=dict)
    unit_trap: dict[str, float] = field(default_factory=dict)
    no_trap: dict[str, float] = field(default_factory=dict)
    by_sector: dict[str, int] = field(default_factory=dict)
    by_fiscal_year: dict[str, int] = field(default_factory=dict)
    final_only_correct: float = 0.0

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "n_items": self.n_items,
            "axes": self.axes,
            "all_axes_correct": self.all_axes_correct,
            "final_only_correct": self.final_only_correct,
            "cancelling_error_gap": round(self.final_only_correct - self.all_axes_correct, 4),
            "by_depth": {str(k): v for k, v in sorted(self.by_depth.items())},
            "unit_trap_subset": self.unit_trap,
            "no_trap_subset": self.no_trap,
            "strata": {"sector": self.by_sector, "fiscal_year": self.by_fiscal_year},
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=False)

    def to_markdown(self) -> str:
        a = self.axes
        lines = [
            f"### {self.model}  (n={self.n_items})",
            "",
            "| retrieval | units | intermediate | final | all four |",
            "|---|---|---|---|---|",
            f"| {a['retrieval']:.3f} | {a['units']:.3f} | {a['intermediate']:.3f} "
            f"| {a['final']:.3f} | **{self.all_axes_correct:.3f}** |",
            "",
            f"Final-answer-only accuracy: {self.final_only_correct:.3f}. "
            f"Gap to all-four-axes: {self.final_only_correct - self.all_axes_correct:+.3f} "
            "(items answered right through a wrong chain).",
            "",
            "| depth | retrieval | units | intermediate | final |",
            "|---|---|---|---|---|",
        ]
        for depth, ax in sorted(self.by_depth.items()):
            lines.append(
                f"| {depth} | {ax['retrieval']:.3f} | {ax['units']:.3f} "
                f"| {ax['intermediate']:.3f} | {ax['final']:.3f} |"
            )
        lines += [
            "",
            f"Unit-trap subset (n={self.unit_trap.get('n', 0):.0f}): "
            f"final {self.unit_trap.get('final', float('nan')):.3f} vs "
            f"{self.no_trap.get('final', float('nan')):.3f} on non-trap items.",
        ]
        return "\n".join(lines)


def build_report(model: str, items: list[Item], preds: dict[str, Prediction]) -> Report:
    """Score every item. A missing prediction scores zero, it is not skipped:
    dropping unanswered items would let a model raise its score by abstaining."""
    if not items:
        raise ValueError("cannot build a report over zero items; an empty split scores 100%")

    per_axis: dict[str, list[tuple[float, int]]] = defaultdict(list)
    per_depth: dict[int, dict[str, list[tuple[float, int]]]] = defaultdict(lambda: defaultdict(list))
    trap: dict[bool, dict[str, list[tuple[float, int]]]] = {True: defaultdict(list), False: defaultdict(list)}
    correct = final_ok = 0
    sectors: dict[str, int] = defaultdict(int)
    years: dict[str, int] = defaultdict(int)

    for item in items:
        pred = preds.get(item.item_id) or Prediction(item_id=item.item_id)
        scores = score_item(item, pred)
        for axis in AXES:
            s: AxisScore = scores[axis]
            n = max(s.n, 1)
            per_axis[axis].append((s.score, n))
            per_depth[item.reasoning_depth][axis].append((s.score, n))
            trap[item.unit_trap][axis].append((s.score, n))
        correct += item_correct(scores)
        final_ok += scores["final"].score == 1.0
        sectors[item.sector] += 1
        years[item.fiscal_year] += 1

    def collapse(d: dict[str, list[tuple[float, int]]]) -> dict[str, float]:
        return {axis: _mean(d[axis]) for axis in AXES if d[axis]}

    n = len(items)
    return Report(
        model=model,
        n_items=n,
        axes=collapse(per_axis),
        all_axes_correct=round(correct / n, 4),
        final_only_correct=round(final_ok / n, 4),
        by_depth={d: collapse(v) for d, v in per_depth.items()},
        unit_trap={**collapse(trap[True]), "n": float(sum(i.unit_trap for i in items))},
        no_trap={**collapse(trap[False]), "n": float(sum(not i.unit_trap for i in items))},
        by_sector=dict(sorted(sectors.items())),
        by_fiscal_year=dict(sorted(years.items())),
    )
