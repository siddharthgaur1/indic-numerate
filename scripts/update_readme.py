#!/usr/bin/env python
"""Regenerate the README's counts block from data/. Run after changing the data.

    python scripts/update_readme.py
    python scripts/update_readme.py --check   # exit 1 if stale (used by CI)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from indic_numerate.stats import current_counts, render_block, replace_block  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    text = README.read_text(encoding="utf-8")
    updated = replace_block(text, render_block(current_counts(ROOT)))
    if updated == text:
        print("README counts are current")
        return 0
    if args.check:
        print("README counts are STALE; run `python scripts/update_readme.py`", file=sys.stderr)
        return 1
    README.write_text(updated, encoding="utf-8")
    print(f"updated {README}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
