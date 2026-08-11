#!/usr/bin/env python
"""Build data/sources.csv from a stated sampling frame.

The frame is an NSE index constituent list (NIFTY 50 by default), not "companies
whose investor-relations site does not block a scraper". That distinction is the
whole point: guessing PDF URLs off company websites returns 403 for most large
Indian issuers, and a corpus assembled from the ones that answer would be
stratified by bot policy -- a sampling frame nobody chose and nobody could state.

Annual report URLs come from NSE's own filing archive, which publishes the PDF
every listed company filed, with the fiscal years it covers. Where a company has
filed a revised submission for a year, the latest submission wins and the
supersession is recorded: a revised annual report is exactly the restatement
situation docs/annotation-guidelines.md section 4 is about.

    python scripts/build_sources.py
    python scripts/build_sources.py --index "NIFTY 50" --from-fy 2022 --to-fy 2025
    python scripts/build_sources.py --dry-run

This writes the source LIST only. It downloads no annual reports; that is
scripts/fetch_reports.py, which records the hash of what it actually got.
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from indic_numerate.units import parse_period  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "data" / "sources.csv"
FRAME = ROOT / "data" / "frame.csv"

INDEX_CSV = "https://nsearchives.nseindia.com/content/indices/ind_{slug}list.csv"
ANNUAL_REPORTS = "https://www.nseindia.com/api/annual-reports?index=equities&symbol={symbol}"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"

# NSE's coarse industry -> this benchmark's sector vocabulary.
INDUSTRY_TO_SECTOR = {
    "information technology": "it_services",
    "healthcare": "pharma",
    "fast moving consumer goods": "fmcg",
    "automobile and auto components": "auto",
    "metals & mining": "metals",
    "oil gas & consumable fuels": "energy",
    "power": "energy",
    "telecommunication": "telecom",
    "construction": "infrastructure",
    "construction materials": "infrastructure",
    "services": "infrastructure",
    "consumer durables": "other",
    "chemicals": "other",
    "consumer services": "other",
    "capital goods": "other",
}

# "Financial Services" covers banks, NBFCs and insurers, which behave very
# differently in a financial statement. Split by hand, because the index does
# not: README limitation 8 records that sector labels are maintainer-assigned.
FINANCIAL_OVERRIDES = {
    "nbfc": {"BAJFINANCE", "BAJAJFINSV", "SHRIRAMFIN", "JIOFIN", "CHOLAFIN", "MUTHOOTFIN", "PFC", "RECLTD"},
    "insurance": {"SBILIFE", "HDFCLIFE", "ICICIGI", "ICICIPRULI", "LICI", "MAXHEALTH"},
}


def session():
    import requests

    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json, text/csv, */*"})
    s.get("https://www.nseindia.com/", timeout=30)  # cookies; the API 401s without them
    return s


def sector_for(symbol: str, industry: str) -> str:
    key = (industry or "").strip().lower()
    if key == "financial services":
        for sector, symbols in FINANCIAL_OVERRIDES.items():
            if symbol in symbols:
                return sector
        return "banking"
    return INDUSTRY_TO_SECTOR.get(key, "other")


def fetch_frame(sess, index: str) -> list[dict]:
    slug = re.sub(r"[^a-z0-9]+", "", index.lower())
    url = INDEX_CSV.format(slug=slug)
    resp = sess.get(url, timeout=60)
    if resp.status_code != 200 or "Company Name" not in resp.text:
        raise SystemExit(
            f"could not read the index constituent list from {url} (HTTP {resp.status_code}). "
            "The frame must be a published constituent list; this script will not fall back "
            "to a hand-picked set of companies."
        )
    rows = list(csv.DictReader(io.StringIO(resp.text)))
    FRAME.write_text(resp.text, encoding="utf-8")
    print(f"frame: {len(rows)} constituents of {index} (saved to {FRAME.relative_to(ROOT)})")
    return rows


def reports_for(sess, symbol: str) -> list[dict]:
    resp = sess.get(ANNUAL_REPORTS.format(symbol=symbol), timeout=60)
    resp.raise_for_status()
    return resp.json().get("data", [])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--index", default="NIFTY 50")
    ap.add_argument("--from-fy", type=int, default=2022, help="earliest fiscal year (FY ending)")
    ap.add_argument("--to-fy", type=int, default=2025, help="latest fiscal year (FY ending)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    sess = session()
    constituents = fetch_frame(sess, args.index)

    rows: dict[tuple[str, str], dict] = {}
    superseded = 0
    for i, c in enumerate(constituents, 1):
        symbol = c["Symbol"].strip()
        company = c["Company Name"].strip()
        sector = sector_for(symbol, c.get("Industry", ""))
        try:
            reports = reports_for(sess, symbol)
        except Exception as exc:
            print(f"  {symbol}: no filings retrieved ({type(exc).__name__}); skipped", file=sys.stderr)
            continue
        kept = 0
        for r in reports:
            url = (r.get("fileName") or "").strip()
            if not url.lower().endswith(".pdf"):
                continue
            try:
                fy = parse_period(f"FY{int(r['toYr'])}")
            except (KeyError, ValueError, TypeError):
                continue
            if not args.from_fy <= int(fy[2:]) <= args.to_fy:
                continue
            key = (symbol, fy)
            broadcast = r.get("broadcast_dttm", "")
            if key in rows:
                superseded += 1
                if broadcast <= rows[key]["_broadcast"]:
                    continue
            rows[key] = {
                "doc_id": f"{symbol.lower()}-{fy.lower()}",
                "company": company,
                "sector": sector,
                "fiscal_year": fy,
                "source_url": url,
                "_broadcast": broadcast,
                "_submission": r.get("submission_type", ""),
            }
            kept += 1
        print(f"[{i}/{len(constituents)}] {symbol:12s} {sector:14s} {kept} report(s)")
        time.sleep(0.3)  # NSE throttles; this is a courtesy, not a workaround

    if not rows:
        raise SystemExit("no annual reports found; refusing to write an empty source list")

    ordered = sorted(rows.values(), key=lambda r: r["doc_id"])
    print(f"\n{len(ordered)} report(s) across {len({r['doc_id'].split('-')[0] for r in ordered})} companies, "
          f"FY{args.from_fy}-FY{args.to_fy}; {superseded} superseded submission(s) dropped")
    if args.dry_run:
        print("--dry-run: nothing written")
        return 0

    with SOURCES.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["doc_id", "company", "sector", "fiscal_year", "source_url"])
        w.writeheader()
        for r in ordered:
            w.writerow({k: r[k] for k in w.fieldnames})
    print(f"wrote {SOURCES.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
