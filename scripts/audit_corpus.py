#!/usr/bin/env python
"""Check every corpus PDF is actually readable, and record what is not.

A SHA-256 proves you have the bytes the publisher served. It does not prove those
bytes are a PDF that opens, or that its pages carry a text layer. At least one
document in this corpus hashes correctly and cannot be parsed at all.

Writes data/corpus_audit.json: per document, whether it opens, its page count,
how many sampled pages yield text, and the error if it failed. Items cannot be
authored from a document that fails here, and anyone reproducing the benchmark
needs to know which ones those are.

    python scripts/audit_corpus.py
    python scripts/audit_corpus.py --sample 12
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from indic_numerate.corpus import load_corpus  # noqa: E402
from indic_numerate.rng import take  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "data" / "corpus.jsonl"
PDF_DIR = ROOT / "data" / "pdfs"
OUT = ROOT / "data" / "corpus_audit.json"


def audit_one(doc_id: str, sample: int) -> dict:
    import pdfplumber

    path = PDF_DIR / f"{doc_id}.pdf"
    row = {"doc_id": doc_id, "opens": False, "n_pages": None,
           "sampled": 0, "pages_with_text": 0, "error": None}
    if not path.is_file():
        row["error"] = "file missing"
        return row
    try:
        with pdfplumber.open(path) as pdf:
            row["opens"] = True
            row["n_pages"] = len(pdf.pages)
            # Seeded sample of pages, never a prefix: front matter is images and
            # a prefix would report every report as text-free.
            pages = take(list(range(len(pdf.pages))), min(sample, len(pdf.pages)),
                         salt=f"audit:{doc_id}")
            row["sampled"] = len(pages)
            for i in pages:
                try:
                    if (pdf.pages[i].extract_text() or "").strip():
                        row["pages_with_text"] += 1
                except Exception:  # a single bad page must not fail the document
                    pass
    except Exception as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sample", type=int, default=8, help="pages to sample per document")
    args = ap.parse_args()

    docs = load_corpus(CORPUS)
    rows = []
    for i, doc in enumerate(docs, 1):
        row = audit_one(doc.doc_id, args.sample)
        rows.append(row)
        flag = "" if row["opens"] and row["pages_with_text"] else "   <-- UNUSABLE"
        print(f"[{i}/{len(docs)}] {doc.doc_id:26s} opens={str(row['opens']):5s} "
              f"pages={row['n_pages']} text={row['pages_with_text']}/{row['sampled']}{flag}", flush=True)

    broken = [r for r in rows if not r["opens"]]
    textless = [r for r in rows if r["opens"] and r["sampled"] and r["pages_with_text"] == 0]
    OUT.write_text(json.dumps({
        "n_documents": len(rows),
        "n_openable": len(rows) - len(broken),
        "n_unopenable": len(broken),
        "n_without_text_layer": len(textless),
        "unusable_doc_ids": sorted(r["doc_id"] for r in broken + textless),
        "documents": rows,
    }, indent=2), encoding="utf-8")

    print(f"\n{len(rows)} documents: {len(rows) - len(broken)} open, {len(broken)} do not, "
          f"{len(textless)} open but have no text layer in the sampled pages")
    for r in broken:
        print(f"  UNOPENABLE {r['doc_id']}: {r['error']}")
    for r in textless:
        print(f"  NO TEXT     {r['doc_id']}: {r['n_pages']} pages, none of {r['sampled']} sampled had text")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
