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

## Corpus as fetched

92 documents, 49 companies, 12 sectors, FY2024–FY2025, ~1.9 GB of PDF. Every one
carries its source URL, fetch date and SHA-256 in `data/corpus.jsonl`;
`python scripts/fetch_reports.py --verify` re-hashes local copies against it and
reports 0 problems as of the fetch.

The PDFs themselves are not committed — they are the publishers', and the hashes
are what makes the corpus reproducible.
