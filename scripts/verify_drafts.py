#!/usr/bin/env python
"""Check every drafted figure against the PDF page its anchor names.

The schema proves a chain is internally consistent. It cannot prove a figure was
read off the right page -- so this does the other half: for each figure in each
item, open the cited page and look for the printed value, in both the Indian
(1,58,381) and Western (158,381) digit groupings that Indian filings mix freely,
and for the unit the item claims the page prints.

This is still not a substitute for review. It confirms the number is ON the page;
a human confirms it is the number the question is about.

    python scripts/verify_drafts.py
    python scripts/verify_drafts.py --items data/items.jsonl
"""

from __future__ import annotations

import argparse
import re
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from indic_numerate.loader import load_items  # noqa: E402
from indic_numerate.units import parse_unit  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PDF_DIR = ROOT / "data" / "pdfs"
DRAFTS = ROOT / "data" / "items_draft.jsonl"

UNIT_WORDS = {
    "crore": r"crore", "lakh": r"lakh|lac", "million": r"million|\bmn\b",
    "billion": r"billion|\bbn\b", "thousand": r"thousand", "rupees": r"rs\.?|inr|₹",
}


def groupings(value: Decimal) -> list[str]:
    """Every way an Indian filing might print this number."""
    s = format(value, "f")
    whole, _, frac = s.partition(".")
    neg = whole.startswith("-")
    whole = whole.lstrip("-")

    western = f"{int(whole):,}"
    # Indian grouping: last three digits, then pairs.
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        indian = ",".join(parts + [tail])
    else:
        indian = whole

    out = []
    for body in {whole, western, indian}:
        text = body + (f".{frac}" if frac else "")
        out.append(text)
        if neg:  # filings print negatives in brackets
            out += [f"({text})", f"-{text}"]
    return out


def page_text(cache: dict, doc_id: str, page: int) -> str | None:
    import pdfplumber

    key = (doc_id, page)
    if key in cache:
        return cache[key]
    path = PDF_DIR / f"{doc_id}.pdf"
    if not path.is_file():
        cache[key] = None
        return None
    with pdfplumber.open(path) as pdf:
        if page > len(pdf.pages):
            cache[key] = None
        else:
            cache[key] = pdf.pages[page - 1].extract_text() or ""
    return cache[key]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--items", default=str(DRAFTS))
    args = ap.parse_args()

    items = load_items(args.items)
    cache: dict = {}
    problems: list[str] = []
    checked = 0

    for item in items:
        for f in item.figures:
            checked += 1
            text = page_text(cache, item.doc_id, f.page)
            if text is None:
                problems.append(f"{item.item_id}/{f.fig_id}: {item.doc_id}.pdf page {f.page} unavailable")
                continue
            flat = re.sub(r"[ \t]+", " ", text)
            if not any(g in flat for g in groupings(f.value_as_printed)):
                problems.append(
                    f"{item.item_id}/{f.fig_id}: {f.value_as_printed} not found on "
                    f"{item.doc_id}.pdf page {f.page} in any digit grouping"
                )
                continue
            unit_pat = UNIT_WORDS.get(f.unit_as_printed)
            if unit_pat and not re.search(unit_pat, flat, re.I):
                problems.append(
                    f"{item.item_id}/{f.fig_id}: page {f.page} does not mention "
                    f"'{f.unit_as_printed}' anywhere; the item claims the page prints in it"
                )
        # the section label should appear on the page too, loosely
        for f in item.figures:
            if f.section:
                text = page_text(cache, item.doc_id, f.page) or ""
                words = [w for w in re.findall(r"[A-Za-z]{4,}", f.section)]
                hit = sum(1 for w in words if re.search(w, text, re.I))
                if words and hit < max(2, len(words) // 2):
                    problems.append(
                        f"{item.item_id}/{f.fig_id}: section {f.section!r} does not match the text "
                        f"of page {f.page} (matched {hit}/{len(words)} words)"
                    )
                break

    for p in problems:
        print("PROBLEM", p)
    print(f"\n{'FAIL' if problems else 'OK'}: {checked} figure(s) checked across {len(items)} item(s), "
          f"{len(problems)} problem(s)")
    if not problems:
        print("Every drafted figure appears on the page its anchor names. That is necessary, "
              "not sufficient: a human still has to confirm it is the right row.")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
