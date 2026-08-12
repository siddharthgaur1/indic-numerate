#!/usr/bin/env python
"""Fetch real annual report PDFs and record provenance.

Reads data/sources.csv (doc_id, company, sector, fiscal_year, source_url),
downloads each PDF to data/pdfs/<doc_id>.pdf, and appends a provenance record
to data/corpus.jsonl.

There is no fallback. A URL that 404s, a file that is not a PDF, or a host that
times out produces an error and a skipped row -- never a placeholder document.

    python scripts/fetch_reports.py                 # fetch everything missing
    python scripts/fetch_reports.py --limit 20      # seeded shuffle, then 20
    python scripts/fetch_reports.py --verify        # re-hash local files
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from indic_numerate.corpus import Document, append, load_corpus, sha256_file, verify  # noqa: E402
from indic_numerate.rng import take  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "data" / "sources.csv"
CORPUS = ROOT / "data" / "corpus.jsonl"
PDF_DIR = ROOT / "data" / "pdfs"
REQUIRED_COLUMNS = {"doc_id", "company", "sector", "fiscal_year", "source_url"}


def read_sources(path: Path) -> list[dict]:
    if not path.is_file():
        raise SystemExit(
            f"{path} not found. It is a CSV with columns {sorted(REQUIRED_COLUMNS)}, one row per "
            "annual report, listing the publisher's own URL for the PDF. Nothing is fetched "
            "without it and nothing is invented in its place."
        )
    with path.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise SystemExit(f"{path} has no rows.")
    missing = REQUIRED_COLUMNS - set(rows[0])
    if missing:
        raise SystemExit(f"{path}: missing required column(s) {sorted(missing)}")
    return rows


# NSE's filing archive silently drops connections from non-browser user agents:
# a plain "indic-numerate/0.1" UA read-times-out on every URL. These are public
# filings published for download, so the fetcher presents a browser UA and keeps
# itself identifiable through the From/X-Contact headers rather than pretending
# to be anonymous. If a publisher asks us to stop, this is where to change it.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "From": "https://github.com/siddharthgaur1/indic-numerate",
    "X-Contact": "https://github.com/siddharthgaur1/indic-numerate",
    "Accept": "application/pdf,*/*",
}


def fetch_one(row: dict, timeout: int) -> Document:
    import requests  # imported late so --verify works without the network stack

    url = row["source_url"].strip()
    resp = requests.get(url, timeout=timeout, headers=HEADERS, stream=True)
    resp.raise_for_status()
    body = b"".join(resp.iter_content(chunk_size=1 << 16))

    # A truncated download hashes perfectly well: the hash records whatever
    # arrived. Six documents in the first run of this fetcher were cut at an
    # exact 32 KiB boundary, stored, hashed, and only found to be unreadable
    # much later. So completeness is checked here, at the only point where the
    # information exists, and a short read is a failure rather than a document.
    declared = resp.headers.get("content-length")
    if declared is not None and int(declared) != len(body):
        raise ValueError(
            f"{row['doc_id']}: truncated download -- server declared {int(declared)} bytes, "
            f"received {len(body)}. Not stored; nothing was substituted for it."
        )
    if not body.startswith(b"%PDF"):
        raise ValueError(
            f"{row['doc_id']}: {url} returned {len(body)} bytes that are not a PDF "
            f"(starts with {body[:16]!r}); the publisher may be serving an interstitial page"
        )
    if b"%%EOF" not in body[-2048:]:
        raise ValueError(
            f"{row['doc_id']}: PDF has no %%EOF trailer in its last 2 KB ({len(body)} bytes "
            "received), so the file is incomplete. Not stored."
        )
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    local = PDF_DIR / f"{row['doc_id']}.pdf"
    local.write_bytes(body)
    return Document(
        doc_id=row["doc_id"].strip(),
        company=row["company"].strip(),
        sector=row["sector"].strip(),
        fiscal_year=row["fiscal_year"].strip(),
        source_url=url,
        fetched_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        sha256=sha256_file(local),
        n_bytes=len(body),
        local_path=str(local.relative_to(ROOT)).replace("\\", "/"),
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, help="fetch at most N (seeded shuffle first, never a prefix)")
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--pause", type=float, default=0.5, help="seconds between downloads")
    ap.add_argument("--verify", action="store_true", help="re-hash local PDFs against data/corpus.jsonl")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.verify:
        problems = verify(load_corpus(CORPUS), PDF_DIR)
        for p in problems:
            print("MISMATCH", p)
        print(f"{'FAIL' if problems else 'OK'}: {len(problems)} problem(s)")
        return 1 if problems else 0

    rows = read_sources(SOURCES)
    already = set()
    if CORPUS.is_file():
        already = {d.doc_id for d in load_corpus(CORPUS)}
    todo = [r for r in rows if r["doc_id"] not in already]
    # Seeded shuffle BEFORE any limit. A prefix of a CSV is a biased sample:
    # source lists are usually grouped by sector or sorted newest-first.
    todo = take(todo, args.limit, salt="fetch")

    print(f"{len(rows)} listed, {len(already)} already fetched, {len(todo)} to fetch")
    if args.dry_run:
        for r in todo:
            print("would fetch", r["doc_id"], r["source_url"])
        return 0

    failures = 0
    for row in todo:
        try:
            doc = fetch_one(row, args.timeout)
        except Exception as exc:  # network, HTTP, validation
            failures += 1
            print(f"FAILED {row['doc_id']}: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        append(CORPUS, doc)
        print(f"ok {doc.doc_id} {doc.n_bytes / 1e6:.1f}MB {doc.sha256[:12]}", flush=True)
        time.sleep(args.pause)  # courtesy to the publisher's archive
    if failures:
        print(f"{failures} document(s) could not be fetched. They are absent from the corpus; "
              "nothing was substituted for them.", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
