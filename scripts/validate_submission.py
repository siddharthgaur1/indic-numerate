#!/usr/bin/env python
"""Validate a submission file before you send it. Run this first.

    python scripts/validate_submission.py my_submission.json
    python scripts/validate_submission.py my_submission.json --no-items   # shape only

Exit status 0 if the file would be accepted, 1 otherwise. Every error names the
prediction it came from.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from indic_numerate.loader import load_items  # noqa: E402
from indic_numerate.submission import SubmissionError, validate  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ITEMS = ROOT / "data" / "items.jsonl"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("submission")
    ap.add_argument("--items", default=str(ITEMS))
    ap.add_argument("--no-items", action="store_true",
                    help="check the file's shape without the benchmark data present")
    args = ap.parse_args()

    expected = None
    if not args.no_items:
        try:
            expected = {i.item_id for i in load_items(args.items, split="test")}
        except FileNotFoundError as exc:
            print(f"{exc}\n\nRe-run with --no-items to check the file's shape only.", file=sys.stderr)
            return 1
    try:
        preds = validate(args.submission, expected)
    except (SubmissionError, FileNotFoundError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1
    scope = "shape only" if expected is None else f"all {len(expected)} test items"
    print(f"OK: {len(preds)} prediction(s), {scope}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
