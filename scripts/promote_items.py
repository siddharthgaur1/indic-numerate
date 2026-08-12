#!/usr/bin/env python
"""Promote reviewed drafts into data/items.jsonl. The one human gate.

data/items_draft.jsonl holds machine-drafted candidates. data/items.jsonl is the
benchmark. Nothing crosses that line automatically: this script requires you to
name the items you have checked against the PDF and to sign the promotion, and it
records who signed and when in data/promotions.jsonl.

    python scripts/promote_items.py --list
    python scripts/promote_items.py infy-fy2024-d01 --reviewed-by "Siddharth Gaur"
    python scripts/promote_items.py --all --reviewed-by "Siddharth Gaur"

Promoted items keep their draft id with the -d suffix stripped, so a promoted
item is visibly distinct from a draft that merely looks reviewed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from indic_numerate.loader import iter_items, load_items  # noqa: E402
from indic_numerate.schema import Item  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DRAFTS = ROOT / "data" / "items_draft.jsonl"
ITEMS = ROOT / "data" / "items.jsonl"
LOG = ROOT / "data" / "promotions.jsonl"


def promoted_id(draft_id: str) -> str:
    """'infy-fy2024-d01' -> 'infy-fy2024-01'. Ids without a draft marker pass through."""
    return re.sub(r"-d(\d+)$", r"-\g<1>", draft_id)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("item_ids", nargs="*")
    ap.add_argument("--all", action="store_true", help="promote every draft (you are asserting you checked them all)")
    ap.add_argument("--reviewed-by", help="who checked these against the PDF")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    drafts = {i.item_id: i for i in load_items(DRAFTS)}

    if args.list:
        existing = {i.item_id for i in iter_items(ITEMS)} if ITEMS.is_file() else set()
        for item_id, item in drafts.items():
            state = "promoted" if promoted_id(item_id) in existing else "draft"
            print(f"  {item_id:26s} {state:9s} {item.split:5s} depth={item.reasoning_depth} "
                  f"trap={str(item.unit_trap):5s} {item.doc_id} p{item.figures[0].page}")
        return 0

    if not args.reviewed_by:
        raise SystemExit(
            "--reviewed-by is required. Promotion is the assertion that a person checked every "
            "figure against the page its anchor names; it is not a file copy."
        )
    wanted = list(drafts) if args.all else args.item_ids
    if not wanted:
        raise SystemExit("name the item ids to promote, or pass --all")
    unknown = [i for i in wanted if i not in drafts]
    if unknown:
        raise SystemExit(f"not in {DRAFTS.name}: {unknown}")

    existing = {i.item_id for i in iter_items(ITEMS)} if ITEMS.is_file() else set()
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    written = 0
    with ITEMS.open("a", encoding="utf-8") as items_fh, LOG.open("a", encoding="utf-8") as log_fh:
        for draft_id in wanted:
            new_id = promoted_id(draft_id)
            if new_id in existing:
                print(f"  {draft_id}: already promoted as {new_id}; skipped")
                continue
            payload = json.loads(drafts[draft_id].model_dump_json())
            payload["item_id"] = new_id
            item = Item.model_validate(payload)  # revalidate under the new id
            items_fh.write(item.model_dump_json() + "\n")
            log_fh.write(json.dumps({
                "draft_id": draft_id, "item_id": new_id,
                "reviewed_by": args.reviewed_by, "promoted_at": now,
            }) + "\n")
            written += 1
            print(f"  promoted {draft_id} -> {new_id}")

    print(f"\n{written} item(s) promoted into {ITEMS.relative_to(ROOT)} by {args.reviewed_by}")
    if written:
        print("Now re-run: python scripts/oracle_ceiling.py && python scripts/update_readme.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
