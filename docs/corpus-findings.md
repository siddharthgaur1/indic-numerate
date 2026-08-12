# Corpus findings

What building the corpus actually turned up. Same file as in indic-reg-bench, and
the same reason for it: the constraints discovered while fetching are part of what
the benchmark measures, and they belong somewhere a reader can find them.

## The obvious approach produces a corpus stratified by bot policy

The first attempt fetched annual reports directly from investor-relations sites,
using the URL patterns those sites publish. Result over 20 candidate URLs from
large Indian issuers:

| outcome | count |
|---|---|
| PDF returned | 1 |
| HTTP 403 (bot blocked) | 6 |
| HTTP 404 (pattern wrong or moved) | 11 |
| read timeout | 1 |
| HTML returned with a 200 | 1 |

Had the corpus been assembled from what came back, its sector mix would have been
decided by which companies' CDNs allow automated requests. That is a sampling
frame nobody chose, nobody could state, and nobody would think to check — the same
shape of failure as a prefix taken from an ordered set.

**Resolution:** the frame is a published index constituent list (NIFTY 50, saved to
`data/frame.csv`), and the PDFs come from NSE's own filing archive, which serves
what every listed company actually filed. Coverage within the frame is then a
property of the exchange's archive, not of 50 different CDN configurations.

## NSE's archive only reaches back two years

The annual-reports API returns recent submissions only, which is why the corpus is
FY2024–FY2025 and README limitation 13 says so. Reaching further back needs a
different source (BSE's archive, or the companies' own sites, which brings the
problem above back).

This bounds what restatement items can look like: they must use comparatives
printed *inside* a report in the corpus, not a comparison between two vintages of
the same company's reporting. `docs/annotation-guidelines.md` section 4 was written
with that constraint in mind.

## Revised filings are common enough to need a rule

One company in the frame had filed a revised annual report for a year already
covered. The rule (`scripts/build_sources.py`) is that the latest submission wins
and the superseded one is dropped rather than kept as a second document — two rows
for one company-year would otherwise let the same content land in both splits.

## One document in the frame is not retrievable

`bajaj-auto-fy2025` is listed in NSE's archive and 404s at the URL the archive
gives. It is **absent from `data/corpus.jsonl`**; nothing was substituted for it,
and the fetcher reported it as a failure rather than continuing quietly. 92 of 93
listed reports are in the corpus.

This is the no-synthetic-fallback rule doing its job on the first real run.

## The archive requires a browser user agent

`nsearchives.nseindia.com` does not reject a custom user agent with a status code;
it accepts the connection and never responds, so a fetcher with a polite
`indic-numerate/0.1` UA read-times-out on every URL and looks like a network
problem. The fetcher therefore sends a browser UA and identifies itself through
`From` and `X-Contact` headers instead, with a pause between downloads. See the
comment at `scripts/fetch_reports.py:HEADERS`.

## A correct hash is not a usable document

The first run of the fetcher stored six documents that hash perfectly against
`data/corpus.jsonl` and cannot be opened at all: `PdfminerException: Unexpected
EOF`. `scripts/fetch_reports.py --verify` reported 0 problems for all 92, because
the hash records whatever arrived — including a truncated download.

Their stored sizes gave it away. Every one was an exact multiple of 32 KiB:

| document | stored (bytes) | / 32 KiB | actual size on refetch |
|---|---|---|---|
| drreddy-fy2025   | 2,916,352  | 89   | 17.4 MB |
| titan-fy2025     | 3,145,728  | 96   | 19.8 MB |
| powergrid-fy2025 | 55,115,776 | 1682 | 93.5 MB |
| wipro-fy2025     | 2,293,760  | 70   | 7.9 MB |
| cipla-fy2025     | 2,785,280  | 85   | (still truncates) |
| maxhealth-fy2025 | 3,407,872  | 104  | 24.8 MB |

A stream cut at a buffer boundary, not a publisher serving short files. The
fetcher read `resp.content` and never checked that what it received was what was
promised, so a partial download became a document with a valid-looking provenance
record. PowerGrid lost 40% of its bytes and still verified.

**Fix:** the fetcher now compares the received length against `Content-Length` and
requires a `%%EOF` trailer in the last 2 KB, and a short read is a failure rather
than a document. `scripts/audit_corpus.py` re-checks the whole corpus by actually
opening every PDF, because that is the only check that would have caught this.

`cipla-fy2025` truncates reproducibly at the same byte on refetch, so it is
absent from the corpus rather than stored broken — which is what the no-fallback
rule is for.

The general lesson, and the reason this file exists: **a provenance check tells
you the bytes did not change, not that they were ever right.** Both checks are
needed, and only one of them was there.

## Corpus as fetched

91 documents, 49 companies, 12 sectors, FY2024–FY2025, ~2.1 GB of PDF. Every one
carries its source URL, fetch date and SHA-256 in `data/corpus.jsonl`;
`python scripts/fetch_reports.py --verify` re-hashes local copies against it and
reports 0 problems, and `python scripts/audit_corpus.py` confirms all 91 open with
a text layer (`data/corpus_audit.json`). Two of the 93 listed reports are absent:
`bajaj-auto-fy2025` (404 at the URL NSE's own archive gives) and `cipla-fy2025`
(truncates reproducibly).

The PDFs themselves are not committed — they are the publishers', and the hashes
are what makes the corpus reproducible.
