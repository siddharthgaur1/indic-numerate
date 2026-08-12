#!/usr/bin/env python
"""Re-label items to match their document's split. The split is authoritative.

When the corpus or the splitting rule changes, an item still carrying its old
split label would quietly put a training document's item in the test set. This
rewrites the labels from data/splits/, and refuses to touch an item whose
document has left the corpus.

    python scripts/sync_item_splits.py --dry-run
    python scripts/sync_item_splits.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from indic_numerate.schema import Item  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SPLIT_DIR = ROOT / "data" / "splits"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--items", default=str(ROOT / "data" / "items.jsonl"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    path = Path(args.items)
    if not path.is_file():
        raise SystemExit(f"{path} not found")
    train = set(json.loads((SPLIT_DIR / "train_ids.json").read_text(encoding="utf-8")))
    test = set(json.loads((SPLIT_DIR / "test_ids.json").read_text(encoding="utf-8")))

    out, changed, orphaned = [], 0, []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        doc = row["doc_id"]
        split = "train" if doc in train else "test" if doc in test else None
        if split is None:
            orphaned.append(f"{row['item_id']}: document {doc} is in no split")
            out.append(row)
            continue
        if row.get("split") != split:
            print(f"  {row['item_id']}: {row.get('split')} -> {split}")
            row["split"] = split
            changed += 1
        out.append(row)

    if orphaned:
        raise SystemExit("refusing to write; some items reference documents outside the splits:\n  "
                         + "\n  ".join(orphaned))
    items = [Item.model_validate(r) for r in out]
    print(f"{changed} item(s) re-labelled of {len(items)}")
    if args.dry_run:
        print("--dry-run: nothing written")
        return 0
    path.write_text("\n".join(i.model_dump_json() for i in items) + "\n", encoding="utf-8")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
