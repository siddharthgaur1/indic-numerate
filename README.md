# indic-numerate

A benchmark for multi-step numerical reasoning over Indian annual reports, scored
by decomposition: every item is scored on four axes separately, and an item counts
as correct only if all four are.

Sibling of [indic-reg-bench](https://github.com/siddharthgaur1/indic-reg-bench)
(regulatory text classification). Same licence, same conventions, same rules about
what may be claimed. Apache-2.0.

> **Status: pre-data.** The schema, guidelines, scorers, harness and validators are
> complete and tested. **No benchmark items exist yet** and no baselines have been
> run. Every number below that depends on items is stated as pending, not
> estimated. Items are authored by hand from real published annual reports; nothing
> in this repository generates a document, a question, or a gold answer.

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
| documents | 0 |
| items | 0 (0 train / 0 test) |
| unit-trap items | 0 |
| reasoning depth | none yet |
| sectors / fiscal years | 0 / 0 |
| seed | 20240917 |
<!-- END GENERATED COUNTS -->

Regenerate with `python scripts/update_readme.py`. `tests/test_readme.py` fails if
this table disagrees with `data/`, so the README cannot quietly go stale.

## Oracle ceiling

**Pending — no items exist yet.**

Before any result is published, `scripts/oracle_ceiling.py` must pass. It attempts
to score the test split using only the question text and metadata, without reading
any document, via three attacks (copy a number from the question, answer the train
median, copy the nearest train question's answer) and compares them to a
permutation baseline. If any attack beats chance by more than the threshold, the
benchmark is circular and results must not be published.

The oracle result belongs next to the headline scores, and this README will carry
it there. Until it has been run on real items, this section says pending.

## Leaderboard

See [LEADERBOARD.md](LEADERBOARD.md). **Empty** — no baselines have been run.
When they are, they will be three models the maintainer did not build.

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
7. **Published reports change.** Companies silently replace PDFs. Every document is
   pinned by SHA-256; `python scripts/fetch_reports.py --verify` tells you whether
   your copy is the one the items were written against.
8. **Sector labels are assigned by the maintainer**, not taken from an exchange
   classification, and coarse ones (`other`) absorb the awkward cases.
9. **Restated figures follow the citing document.** An item anchored on the FY2023
   report uses FY2023's restated comparatives, which may differ from what the
   FY2022 report published. This is a deliberate choice, documented in the
   guidelines, and it means the benchmark measures reading, not reconciliation.
10. **Adapters are thin.** No retrieval pipeline, no agent scaffolding, no tools.
    Numbers here are for a model answering from a document reference, and they are
    not comparable to a full RAG system's.

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
  submission.md
scripts/
  fetch_reports.py      fetch real PDFs, record provenance
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
pytest                                   # 200+ tests, no network, no API keys

python scripts/fetch_reports.py          # needs data/sources.csv
python scripts/build_splits.py
python scripts/oracle_ceiling.py         # must pass before any result is published
python scripts/run_eval.py --adapter ollama:llama3.2
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
