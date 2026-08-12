#!/usr/bin/env python
"""Read a corpus document while authoring. Search it, dump a page, resolve scope.

Annual reports print "Statement of Profit and Loss" identically in the standalone
and the consolidated section, often with the only marker several pages earlier.
docs/annotation-guidelines.md section 6 says an item whose scope is not pinned
must be dropped -- so this tool resolves the scope from the section divider
rather than leaving it to memory.

    python scripts/inspect_doc.py infy-fy2025 --find "Statement of Profit and Loss"
    python scripts/inspect_doc.py infy-fy2025 --page 197
    python scripts/inspect_doc.py infy-fy2025 --sections
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from indic_numerate.corpus import load_corpus  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "data" / "corpus.jsonl"
PDF_DIR = ROOT / "data" / "pdfs"

# A section divider is a page whose text ANNOUNCES the section, not one that
# merely mentions the word: "Consolidated Financial Statements" as a heading.
DIVIDER = re.compile(
    r"^(?P<scope>Consolidated|Standalone)\s+(Financial Statements?|Balance Sheet)",
    re.I | re.M,
)
SCOPE_WORD = re.compile(r"\b(Consolidated|Standalone)\b", re.I)


def open_pdf(doc_id: str):
    import pdfplumber

    doc = next((d for d in load_corpus(CORPUS) if d.doc_id == doc_id), None)
    if doc is None:
        raise SystemExit(f"{doc_id!r} is not in the corpus; run scripts/build_sources.py and fetch_reports.py")
    path = PDF_DIR / f"{doc_id}.pdf"
    if not path.is_file():
        raise SystemExit(f"{path} is missing. Fetch it with scripts/fetch_reports.py; nothing here invents one.")
    return doc, pdfplumber.open(path)


def scope_map(pdf) -> dict[int, str]:
    """page index -> scope in force, from the last divider at or before it."""
    out: dict[int, str] = {}
    current = "unknown"
    for i, page in enumerate(pdf.pages, 1):
        text = page.extract_text() or ""
        m = DIVIDER.search(text)
        if m:
            current = m.group("scope").lower()
        out[i] = current
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("doc_id")
    ap.add_argument("--find", help="regex to search for")
    ap.add_argument("--page", type=int, help="dump one page")
    ap.add_argument("--chars", type=int, default=1600)
    ap.add_argument("--sections", action="store_true", help="show where each scope begins")
    args = ap.parse_args()

    doc, pdf = open_pdf(args.doc_id)
    with pdf:
        print(f"{doc.doc_id}: {doc.company} {doc.fiscal_year} [{doc.sector}] {len(pdf.pages)} pages")
        print(f"source: {doc.source_url}")
        scopes = scope_map(pdf) if (args.sections or args.find or args.page) else {}

        if args.sections:
            last = None
            for page, scope in scopes.items():
                if scope != last:
                    print(f"  page {page:4d}: {scope} section begins")
                    last = scope
            return 0

        if args.page:
            text = pdf.pages[args.page - 1].extract_text() or ""
            print(f"--- page {args.page} (scope in force: {scopes.get(args.page)}) ---")
            print(text[: args.chars])  # not-a-sample: truncating a page dump for reading
            return 0

        if args.find:
            pattern = re.compile(args.find, re.I)
            for page, scope in scopes.items():
                text = pdf.pages[page - 1].extract_text() or ""
                if pattern.search(text):
                    unit = ""
                    m = re.search(r"\((?:In\s+)?[^)]*(?:crore|lakh|million|billion)[^)]*\)", text, re.I)
                    if m:
                        unit = f"  unit-header: {m.group(0)[:60]}"
                    print(f"  page {page:4d}  scope={scope:12s}{unit}")
            return 0

        ap.error("give one of --find, --page or --sections")


if __name__ == "__main__":
    raise SystemExit(main())
