#!/usr/bin/env python
"""Evaluate a model through an adapter, or score an existing submission.

    python scripts/run_eval.py --adapter ollama:llama3.2
    python scripts/run_eval.py --adapter anthropic:claude-sonnet-5 --limit 20
    python scripts/run_eval.py --submission theirs.json --model "vendor/model"

Results go to results/<model>.json and the leaderboard is regenerated from that
directory. Responses are cached by (item, model version, prompt), so re-scoring
after a scorer change costs nothing.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from indic_numerate import adapters  # noqa: E402
from indic_numerate.loader import load_items  # noqa: E402
from indic_numerate.report import build_report  # noqa: E402
from indic_numerate.rng import take  # noqa: E402
from indic_numerate.runner import run  # noqa: E402
from indic_numerate.submission import validate  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ITEMS = ROOT / "data" / "items.jsonl"
RESULTS = ROOT / "results"
LEADERBOARD = ROOT / "LEADERBOARD.md"


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def rebuild_leaderboard() -> None:
    rows = []
    for path in sorted(RESULTS.glob("*.json")):
        r = json.loads(path.read_text(encoding="utf-8"))
        a = r["axes"]
        rows.append(
            (r["all_axes_correct"], f"| {r['model']} | {r['n_items']} | {a['retrieval']:.3f} | "
             f"{a['units']:.3f} | {a['intermediate']:.3f} | {a['final']:.3f} | "
             f"**{r['all_axes_correct']:.3f}** | {r['cancelling_error_gap']:+.3f} | "
             f"{r['unit_trap_subset'].get('final', float('nan')):.3f} |")
        )
    rows.sort(key=lambda x: -x[0])
    header = [
        "# Leaderboard",
        "",
        "`all four` is the headline: an item counts only if retrieval, units,",
        "intermediates and the final answer are all correct. `cancel gap` is",
        "final-only accuracy minus all-four accuracy -- the rate of right answers",
        "reached through a wrong chain. `trap final` is the final-axis score on the",
        "unit-trap subset alone, never folded into the headline.",
        "",
        "| model | n | retrieval | units | intermediate | final | all four | cancel gap | trap final |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    body = [r[1] for r in rows] or ["| _no results yet_ | | | | | | | | |"]
    LEADERBOARD.write_text("\n".join(header + body) + "\n", encoding="utf-8")
    print(f"wrote {LEADERBOARD} ({len(rows)} row(s))")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--adapter", help="e.g. ollama:llama3.2, anthropic:claude-sonnet-5")
    ap.add_argument("--submission", help="score a submission file instead of calling a model")
    ap.add_argument("--model", help="label for a --submission run (defaults to the file's model field)")
    ap.add_argument("--items", default=str(ITEMS))
    ap.add_argument("--split", default="test", choices=["train", "test"])
    ap.add_argument("--limit", type=int, help="evaluate a seeded random subset (never a prefix)")
    ap.add_argument("--cache-dir", default=str(ROOT / ".cache"))
    ap.add_argument("--leaderboard-only", action="store_true")
    args = ap.parse_args()

    if args.leaderboard_only:
        rebuild_leaderboard()
        return 0
    if bool(args.adapter) == bool(args.submission):
        ap.error("give exactly one of --adapter or --submission")

    items = load_items(args.items, split=args.split)
    items = take(items, args.limit, salt=f"eval:{args.split}")

    if args.submission:
        preds = validate(args.submission, {i.item_id for i in items} if not args.limit else None)
        model = args.model or json.loads(Path(args.submission).read_text(encoding="utf-8"))["model"]
    else:
        adapter = adapters.build(args.adapter)
        preds = run(items, adapter, args.cache_dir)
        model = adapter.name

    report = build_report(model, items, preds)
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"{slug(model)}.json"
    out.write_text(report.to_json(), encoding="utf-8")
    print("\n" + report.to_markdown())
    print(f"\nwrote {out}")
    rebuild_leaderboard()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
