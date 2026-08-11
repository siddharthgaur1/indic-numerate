#!/usr/bin/env python
"""Authoring CLI. Draws a document, opens a template, validates what you wrote.

This tool does not write questions or gold answers. It draws documents in a
seeded order, restricted to one split, hands you a skeleton to fill in, and
refuses anything the schema rejects.

    python scripts/write_items.py --split train
    python scripts/write_items.py --split train --count 5
    python scripts/write_items.py --split train --dry-run   # show the draw order

Resumability: the draw order is a pure function of the shared seed, so stopping
and restarting continues where you left off. Documents that already have the
target number of items are skipped, not redrawn -- and no unseeded prefix is
ever taken (see indic_numerate.rng).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from indic_numerate.corpus import load_corpus  # noqa: E402
from indic_numerate.loader import iter_items  # noqa: E402
from indic_numerate.rng import SEED, take  # noqa: E402
from indic_numerate.schema import Item  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "data" / "corpus.jsonl"
ITEMS = ROOT / "data" / "items.jsonl"
SPLIT_DIR = ROOT / "data" / "splits"

TEMPLATE = {
    "item_id": "<doc_id>-01",
    "question": "",
    "doc_id": "",
    "figures": [
        {"fig_id": "f1", "label": "", "value_as_printed": "0", "unit_as_printed": "crore",
         "page": 1, "section": "", "period": "FY2023", "restated": False},
        {"fig_id": "f2", "label": "", "value_as_printed": "0", "unit_as_printed": "crore",
         "page": 1, "section": "", "period": "FY2022", "restated": False},
    ],
    "steps": [
        {"step_id": "s1", "description": "", "operation": "subtract", "inputs": ["f1", "f2"],
         "value": "0", "unit": "crore"},
        {"step_id": "s2", "description": "", "operation": "percent_change", "inputs": ["s1", "f2"],
         "value": "0", "unit": "percent"},
    ],
    "final_value": "0",
    "final_unit": "percent",
    "tolerance": {"mode": "absolute", "value": "0.05"},
    "reasoning_depth": 2,
    "unit_trap": False,
    "sector": "",
    "fiscal_year": "",
    "split": "",
}

HINTS = """\
// docs/annotation-guidelines.md is the authority. Reminders:
//   * every figure must be used by a step; decoys are rejected
//   * reasoning_depth == len(steps); the last step IS the final answer
//   * unit_trap is derived -- set it wrong and the item is rejected
//   * tolerance: relative for money, absolute for ratios/percentages
//   * restated figures need a restatement_note
//   * ambiguous? drop it. Log it in data/drops.jsonl with a reason.
// Delete these comment lines before saving, or leave them -- they are stripped.
"""


def load_split_ids(split: str) -> set[str]:
    path = SPLIT_DIR / f"{split}_ids.json"
    if not path.is_file():
        raise SystemExit(
            f"{path} not found. Run `python scripts/build_splits.py` first; authoring draws "
            "only from the split it was told to, and an unsplit corpus has no such pool."
        )
    return set(json.loads(path.read_text(encoding="utf-8")))


def existing_counts() -> Counter:
    if not ITEMS.is_file():
        return Counter()
    return Counter(i.doc_id for i in iter_items(ITEMS))


def draw(split: str, per_doc: int) -> list:
    docs = [d for d in load_corpus(CORPUS) if d.doc_id in load_split_ids(split)]
    if not docs:
        raise SystemExit(f"no documents in split {split!r}")
    # Seeded shuffle of the WHOLE pool before anything is taken from it. The
    # corpus file is in fetch order, which correlates with sector and year.
    ordered = take(sorted(docs, key=lambda d: d.doc_id), None, salt=f"author:{split}")
    have = existing_counts()
    return [d for d in ordered if have[d.doc_id] < per_doc]


def edit(payload: dict) -> dict | None:
    editor = os.environ.get("EDITOR") or ("notepad" if os.name == "nt" else "nano")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
        fh.write(HINTS + json.dumps(payload, indent=2))
        tmp = fh.name
    subprocess.call([editor, tmp])
    text = "\n".join(l for l in Path(tmp).read_text(encoding="utf-8").splitlines() if not l.strip().startswith("//"))
    Path(tmp).unlink(missing_ok=True)
    if not text.strip():
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        print(f"  not valid JSON ({exc.msg} at line {exc.lineno}); item discarded", file=sys.stderr)
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", required=True, choices=["train", "test"])
    ap.add_argument("--count", type=int, default=1, help="how many items to author this session")
    ap.add_argument("--per-doc", type=int, default=1, help="target items per document")
    ap.add_argument("--dry-run", action="store_true", help="print the draw order and exit")
    args = ap.parse_args()

    pool = draw(args.split, args.per_doc)
    print(f"seed={SEED} split={args.split}: {len(pool)} document(s) still needing items")
    if args.dry_run:
        for d in pool[: args.count]:  # sampling-frame: shuffled by draw() via rng.take, filtering preserves order
            print(f"  {d.doc_id:32s} {d.company} {d.fiscal_year} [{d.sector}]")
        print("--dry-run: nothing written")
        return 0

    written = 0
    for doc in pool[: args.count]:  # sampling-frame: shuffled by draw() via rng.take, so a prefix is resumable
        print(f"\n[{written + 1}/{args.count}] {doc.doc_id} -- {doc.company} {doc.fiscal_year} ({doc.sector})")
        print(f"  PDF: {doc.local_path}  source: {doc.source_url}")
        seq = existing_counts()[doc.doc_id] + 1
        payload = json.loads(json.dumps(TEMPLATE))
        payload.update(
            item_id=f"{doc.doc_id}-{seq:02d}",
            doc_id=doc.doc_id,
            sector=doc.sector,
            fiscal_year=doc.fiscal_year,
            split=args.split,
        )
        raw = edit(payload)
        if raw is None:
            print("  skipped")
            continue
        try:
            item = Item.model_validate(raw)
        except Exception as exc:
            print(f"  REJECTED: {exc}", file=sys.stderr)
            continue
        if item.split != args.split:
            print(f"  REJECTED: item split {item.split!r} is not the split being authored", file=sys.stderr)
            continue
        with ITEMS.open("a", encoding="utf-8") as fh:
            fh.write(item.model_dump_json() + "\n")
        written += 1
        print(f"  wrote {item.item_id} (depth {item.reasoning_depth}, unit_trap={item.unit_trap})")

    print(f"\n{written} item(s) written to {ITEMS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
