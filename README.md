# indic-numerate

A benchmark for multi-step numerical reasoning over Indian annual reports, scored
by decomposition: every item is scored on four axes separately, and an item counts
as correct only if all four are.

Sibling of [indic-reg-bench](https://github.com/siddharthgaur1/indic-reg-bench)
(regulatory text classification). Same licence, same conventions, same rules about
what may be claimed. Apache-2.0.

> **Status: corpus fetched, items are drafts only.** The schema, guidelines,
> scorers, harness and validators are complete and tested, and the corpus is real:
> 91 annual reports from 49 NIFTY 50 companies, each pinned by SHA-256
> (`data/corpus.jsonl`), every one confirmed to open with a text layer, split
> train/test.
>
> **`data/items.jsonl` holds 10 items (6 train / 4 test), and they have NOT been
> page-level human reviewed.** They were machine-drafted, auto-verified to appear
> on the pages they cite (26/26 figures), arithmetically recomputed in Decimal by
> test, and then promoted on the maintainer's instruction. `data/promotions.jsonl`
> records that explicitly: no reviewer has confirmed that each figure is the row
> its question means. Until someone does, treat these as provisional gold — and
> the leaderboard stays empty.

---

## Why decomposition scoring

LLMs retrieve the right figures from financial documents and then compute wrong.
A benchmark that scores only the final answer cannot tell you which happened, and
it cannot tell a right answer from a right answer reached by two cancelling errors.

Indian filings compound the problem: lakh and crore notation, April–March fiscal
years, prior-period figures restated after Ind AS transitions and demergers, and a
single report that prints its P&L in crore and its segment table in lakh. Existing
finance benchmarks are US-centric and single-score, so none of this is separable.

Every item is therefore scored on four axes:

| axis | question it answers |
|---|---|
| **retrieval** | were the correct source figures located (digits only, unit ignored) |
| **units** | was lakh/crore/million and FY-vs-CY handled correctly |
| **intermediate** | are the intermediate values right |
| **final** | is the final number right within tolerance |

`all four` is the headline metric. The gap between final-answer-only accuracy and
all-four accuracy is reported as **cancel gap**: the rate at which a model reaches
the right number through a wrong chain. A benchmark that hides that number is
reporting a mixture of skill and luck.

This is enforced by the schema, not by convention:

* every declared figure must be consumed by a step (no decoy gold),
* `reasoning_depth` must equal the number of steps,
* the final answer must *be* the last step, so it cannot be computed off-chain,
* `unit_trap` is derived from the item's own figures and steps, and an item whose
  declared flag disagrees is rejected,
* tolerance mode is fixed by the answer's unit — relative for money, absolute for
  ratios and percentages.

An item that cannot be scored on all four axes does not parse.

## Corpus at a glance

<!-- BEGIN GENERATED COUNTS -->
| | |
|---|---|
| documents | 91 |
| items | 10 (6 train / 4 test) |
| unit-trap items | 5 |
| reasoning depth | 2-step: 6, 3-step: 1, 4-step: 3 |
| sectors / fiscal years | 12 / 2 |
| seed | 20240917 |
<!-- END GENERATED COUNTS -->

Regenerate with `python scripts/update_readme.py`. `tests/test_readme.py` fails if
this table disagrees with `data/`, so the README cannot quietly go stale.

## Oracle ceiling

**Run on the 10 items: all three attacks score 0.000 against a chance baseline of
0.069, so nothing beats chance. This number is not yet meaningful.**

```
permutation baseline (chance) : 0.069
question-numbers              : 0.000  (-0.069 vs chance)
train-prior                   : 0.000  (-0.069 vs chance)
nearest-question              : 0.000  (-0.069 vs chance)
```

With 6 train and 4 test items, the test split is far too small for this to say
anything about the benchmark. A clean oracle result over four items is what you
would expect from four items that happen not to leak; it is not evidence that a
hundred items will not. **The number to quote is the one from the full item set,
and it does not exist yet.** Reproduce with:

```bash
python scripts/oracle_ceiling.py
```

The gate itself is real: `scripts/oracle_ceiling.py` attempts to score the test
split using only question text and metadata, without reading any document, via
three attacks (copy a number from the question, answer the train median, copy the
nearest train question's answer). If any beats chance by more than the threshold,
the benchmark is circular and results must not be published. `scripts/export_hf.py`
refuses to publish if it fails.

## Leaderboard

See [LEADERBOARD.md](LEADERBOARD.md). **Empty, and it stays empty until items are
reviewed.** A leaderboard built on unreviewed gold would be the exact thing this
repository exists to avoid.

### Provisional baseline (not a result)

One model has been run, over the 4 draft test items, with the document supplied as
the anchored pages plus four seeded distractor pages:

| model | n | retrieval | units | intermediate | final | all four |
|---|---|---|---|---|---|---|
| ollama/llama3.2 (3B) | 4 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |

Two of the four responses were not valid JSON; of the two that parsed, the model
reported figures that appear nowhere in the document (`19 thousand`, `10 lakh`)
and omitted a final answer entirely. So the zero is a genuine failure to do the
task, not a harness artifact — but n=4, on unreviewed items, with a 3B model, is
worth nothing as a published number. It lives in `results/provisional/` and is
excluded from the leaderboard by `--provisional`.

The two API adapters ship and are tested, but **no API-model baseline has been
run**: no API key was available in this environment, and a number nobody produced
is not a number this README will print.

## Limitations

These are load-bearing. They stay in this file; diluting one is a regression.

1. **Single-document items only.** Every item is answerable from one annual report.
   Cross-document arithmetic would conflate retrieval failure with
   document-selection failure, and the retrieval axis could then not separate them.
2. **No OCR.** Figures available only as images are dropped. The benchmark measures
   reasoning, not text extraction, and items whose figures are unreadable are not
   items.
3. **Text-layer PDFs only, and page anchors are PDF indices**, not the folio
   printed on the page. Annual reports have unnumbered front matter.
4. **Reasoning depth is capped at 4 steps.** Longer chains exist in practice; they
   are excluded because gold values become unreliable to self-agree on.
5. **The gold chain is one valid decomposition, not the only one.** A model that
   computes a correct answer by a different but equally valid route will score
   below its true ability on the intermediate axis. Items are written to minimise
   this, but it is not eliminated, and the intermediate axis should be read with it
   in mind.
6. **Single annotator.** Labels are one person's, with a 24-hour-delayed
   self-agreement pass (docs/annotation-guidelines.md §8). There is no
   inter-annotator agreement figure and there will not be one until a second
   annotator exists.
7. **Published reports change, and a hash does not prove a document is usable.**
   Every document is pinned by SHA-256, and `scripts/fetch_reports.py --verify`
   tells you whether your copy is the one the items were written against. It does
   not tell you the PDF opens: six documents in the first fetch were truncated
   mid-download, hashed correctly, and verified clean while being unreadable.
   `scripts/audit_corpus.py` opens every PDF and is the check that catches that;
   `data/corpus_audit.json` records the result (91/91 open with a text layer).
8. **Sector labels come from NSE's own industry column, with one hand-made
   split.** The index lumps banks, NBFCs and insurers into "Financial Services";
   that one is split by the maintainer against a symbol list in
   `scripts/build_sources.py`, and it is judgement, not classification. Coarse
   NSE industries (`Consumer Durables`, `Chemicals`, `Services`) collapse to
   `other`, so `other` is a bucket, not a sector.
9. **Restated figures follow the citing document.** An item anchored on the FY2023
   report uses FY2023's restated comparatives, which may differ from what the
   FY2022 report published. This is a deliberate choice, documented in the
   guidelines, and it means the benchmark measures reading, not reconciliation.
10. **Adapters are thin.** No retrieval pipeline, no agent scaffolding, no tools.
    Numbers here are for a model answering from a document reference, and they are
    not comparable to a full RAG system's.
11. **The corpus frame is one index, large-cap only.** Documents come from the
    NIFTY 50 constituent list as published by NSE (`data/frame.csv`), so mid-cap
    and small-cap reporting practice is absent — and those are where the messier
    unit notation lives. The frame is stated rather than convenient: guessing PDF
    URLs off investor-relations sites returns 403 for most large Indian issuers,
    and a corpus built that way would be stratified by bot policy.
12. **Constituents are as of the fetch date, not as of each fiscal year.** A
    company that entered the index recently is included for earlier years too, and
    one that left is absent. This is survivorship bias in the corpus, and it is not
    corrected.
13. **Fiscal years are limited to FY2024–FY2025.** NSE's filing archive serves only
    recent submissions, so the corpus cannot reach further back without a different
    source. Restatement items are therefore limited to comparatives printed inside
    those reports.
14. **Where a company filed a revised annual report, only the latest submission is
    in the corpus.** The superseded filing is dropped, not recorded as a second
    document.
15. **How much document a model sees changes what `retrieval` means.** The runner
    has three context modes (`none`, `anchored`, `distractors`) and scores across
    them are not comparable. `anchored` hands the model the exact pages the gold
    cites, which makes retrieval an upper bound: a real system has to find those
    pages first. The mode is recorded in the model's name on every result.
16. **The current items are machine-drafted and have not been page-level human
    reviewed.** Their figures are verified to appear on the cited page
    (`scripts/verify_drafts.py`, 26/26) and their arithmetic is recomputed by test,
    but nobody has confirmed that each figure is the row its question means —
    consolidated vs standalone, "revenue" vs "revenue net of GST",
    attributable-to-owners vs total. They were promoted on instruction, and
    `data/promotions.jsonl` says so in the reviewer field. This is the weakest
    claim in the repository and it should be fixed before anything is published.

## Repository layout

```
src/indic_numerate/
  schema.py       item schema; the four-axis decomposition is enforced here
  loader.py       JSONL loading; fails loudly, never substitutes
  units.py        lakh/crore/million and FY-vs-CY normalisation (most-tested module)
  scoring.py      the four scorers, independently testable
  report.py       per-axis, per-depth, unit-trap-subset aggregation
  runner.py       prompt, cache, parse
  adapters.py     Anthropic, OpenAI, Ollama, echo
  submission.py   submission format and validator
  splits.py       seeded, per-stratum, document-level splits
  rng.py          the seed, stated once
  corpus.py       document provenance (URL, fetch date, SHA-256)
docs/
  annotation-guidelines.md
  corpus-findings.md          what building the corpus turned up
  bugs-that-looked-like-results.md
  submission.md
scripts/
  build_sources.py      source list from a published index constituent frame
  fetch_reports.py      fetch real PDFs, record provenance, reject short reads
  audit_corpus.py       open every PDF; a correct hash is not a usable document
  build_splits.py       stratified seeded splits
  write_items.py        authoring CLI (maintainer only)
  oracle_ceiling.py     circularity check; must pass before publishing
  run_eval.py           evaluate a model or score a submission
  validate_submission.py
  update_readme.py
  export_hf.py
```

## Getting started

```bash
pip install -e ".[dev]"
pytest                                   # 260+ tests, no network, no API keys

python scripts/build_sources.py          # source list from the NIFTY 50 frame
python scripts/fetch_reports.py          # ~1.9 GB of real PDFs, hashed as fetched
python scripts/fetch_reports.py --verify # confirm your copies match the corpus index
python scripts/audit_corpus.py           # confirm they actually open (a hash will not)
python scripts/build_splits.py

python scripts/draft_items.py            # candidate items -> data/items_draft.jsonl
python scripts/verify_drafts.py          # every figure must be on the page it cites
python scripts/promote_items.py --list   # review, then promote with --reviewed-by
python scripts/oracle_ceiling.py         # must pass before any result is published
python scripts/run_eval.py --adapter ollama:llama3.2 --context distractors
```

Authoring your own items instead:

```bash
python scripts/write_items.py --split train      # seeded draw, resumable
python scripts/inspect_doc.py infy-fy2025 --sections
```

## Submitting

Read [docs/submission.md](docs/submission.md), then:

```bash
python scripts/validate_submission.py my_submission.json
```

Submissions must cover the whole test split. Partial submissions are rejected
rather than scored over what was supplied.

## Design notes and divergences from indic-reg-bench

Reused: Apache-2.0 (the patent grant matters for an artifact others build on),
`src/` layout, `docs/annotation-guidelines.md` structure, JSONL data files,
document-level split ids in `data/splits/`, error-path tests as a first-class
suite, provenance conventions from nse-warehouse (raw-bytes hash, URL as fetched,
UTC ISO-8601 fetch date).

Diverged, with reasons, in
[docs/annotation-guidelines.md §9](docs/annotation-guidelines.md): gold is a chain
rather than a label; `unit_trap` is machine-derived rather than annotator-asserted;
no abstention task; single-document items only; per-item tolerance; page anchors
are PDF indices.

## Licence

Apache-2.0, matching indic-reg-bench.
