#!/usr/bin/env python
"""Export the benchmark for the HuggingFace dataset mirror.

Writes release/ with one JSONL per split plus a dataset card. Uploading needs
the optional `hf` extra and a token, and only the maintainer runs it.

    python scripts/export_hf.py
    python scripts/export_hf.py --upload siddharthgaur1/indic-numerate

The export refuses to run on an empty item set, and it refuses to publish
before scripts/oracle_ceiling.py has passed: a mirror is a publication.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from indic_numerate.loader import load_items  # noqa: E402
from indic_numerate.stats import current_counts  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ITEMS = ROOT / "data" / "items.jsonl"
RELEASE = ROOT / "release"


def dataset_card(counts: dict) -> str:
    return f"""---
license: apache-2.0
task_categories: [question-answering]
language: [en]
tags: [finance, india, numerical-reasoning, benchmark]
---

# indic-numerate

Multi-step numerical reasoning over Indian annual reports, scored by
decomposition on four axes: retrieval, units, intermediate, final. An item counts
as correct only if all four are.

Source: https://github.com/siddharthgaur1/indic-numerate

| | |
|---|---|
| items | {counts['items']} ({counts['train_items']} train / {counts['test_items']} test) |
| documents | {counts['documents']} |
| unit-trap items | {counts['unit_trap_items']} |
| seed | {counts['seed']} |

**The PDFs are not redistributed here.** Each item references a `doc_id` whose
provenance (publisher URL, fetch date, SHA-256) is in `corpus.jsonl`. Fetch them
yourself with `scripts/fetch_reports.py`; the hashes tell you whether your copy is
the one the items were written against.

Read the limitations in the repository README before quoting any number from this
dataset. They are load-bearing, not boilerplate.
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--upload", metavar="REPO_ID", help="push to the HuggingFace hub")
    ap.add_argument("--skip-oracle", action="store_true", help="not for publication runs")
    args = ap.parse_args()

    items = load_items(ITEMS)  # raises with instructions if absent
    counts = current_counts(ROOT)
    if not args.skip_oracle:
        rc = subprocess.call([sys.executable, str(ROOT / "scripts" / "oracle_ceiling.py")])
        if rc != 0:
            print("oracle ceiling did not pass; refusing to export a circular benchmark", file=sys.stderr)
            return 1

    RELEASE.mkdir(exist_ok=True)
    for split in ("train", "test"):
        rows = [i for i in items if i.split == split]
        (RELEASE / f"{split}.jsonl").write_text(
            "\n".join(i.model_dump_json() for i in rows) + "\n", encoding="utf-8"
        )
        print(f"wrote release/{split}.jsonl ({len(rows)} items)")
    (RELEASE / "corpus.jsonl").write_text(
        (ROOT / "data" / "corpus.jsonl").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (RELEASE / "README.md").write_text(dataset_card(counts), encoding="utf-8")
    print("wrote release/README.md (dataset card)")

    if args.upload:
        from huggingface_hub import HfApi

        HfApi().upload_folder(repo_id=args.upload, repo_type="dataset", folder_path=str(RELEASE))
        print(f"uploaded to https://huggingface.co/datasets/{args.upload}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
