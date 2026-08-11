# Annotation Guidelines

indic-numerate items are written by hand against real published Indian annual
reports. This document is the artifact that decides whether the labels are worth
anything; the schema in `src/indic_numerate/schema.py` mechanically enforces the
parts of it that can be enforced, and the rest is on the annotator.

Structure follows `indic-reg-bench/docs/annotation-guidelines.md`. Divergences
from that document are listed in section 9.

## 1. Sources of truth

1. The PDF as published by the company, fetched by `scripts/fetch_reports.py`
   and pinned by SHA-256. Not a summary, not a news write-up, not a data vendor.
2. The page number printed in the PDF's own page furniture is **not** the
   anchor. `page` is the 1-based index of the page in the PDF file, because that
   is what a harness can address. Where the two differ, record the PDF index.
3. If the figure needed is only in a table image with no text layer, drop the
   item. We are not benchmarking OCR.
4. Consolidated statements unless the question says standalone. If a company
   reports both and the question does not disambiguate, the item is ambiguous
   (section 6) and is dropped.

## 2. Field definitions

| Field | Meaning |
|---|---|
| `question` | Natural language, answerable from one document. Must not contain the answer or any intermediate value (section 7). |
| `doc_id` | Key into `data/corpus.jsonl`, which carries URL, fetch date and hash. |
| `figures[]` | Every figure the model must **retrieve**, recorded exactly as printed. This is the retrieval gold. |
| `figures[].value_as_printed` | The digits on the page. `1,234.5` is recorded as `1234.5`. Never pre-converted. |
| `figures[].unit_as_printed` | The unit the *page* uses, from its column header or table caption, not the unit you would prefer. |
| `figures[].period` | `FY2023`, `CY2022`, `Q3FY2024`. `FY2023` means the year ending 31 March 2023. |
| `figures[].restated` | See section 4. Requires `restatement_note`. |
| `steps[]` | The reasoning chain. Each step's `inputs` are `fig_id`s or *earlier* `step_id`s: the chain must close over the figures. |
| `final_value` / `final_unit` | Must equal the last step exactly. The schema rejects any item where they do not. |
| `tolerance` | `relative` for monetary answers, `absolute` for ratios and percentages. Enforced. See README. |
| `reasoning_depth` | 2, 3 or 4. Equals `len(steps)`. Not an estimate: the schema rejects a mismatch. |
| `unit_trap` | **Derived, never asserted.** True iff the figures use more than one printed unit, or a step is a `convert`, or the figures mix FY and CY basis. The schema recomputes it and rejects a wrong flag. |
| `sector`, `fiscal_year` | Stratification keys, together with `reasoning_depth`. All three must survive to every consumer (`tests/test_stratification.py`). |

## 3. What counts as a reasoning step

A step is **one arithmetic operation over named inputs**. The test is: could a
scorer check this value on its own, without recomputing the whole chain? If yes,
it is a step.

- Retrieving a figure is **not** a step. Retrieval is a separate scoring axis.
  An item whose reasoning is "read one number" has depth 0 and does not belong
  in this benchmark.
- A unit conversion **is** a step (`operation: "convert"`), and declaring one
  forces `unit_trap = true`. This is deliberate: conversions are exactly the
  failure we are trying to isolate, so they are never folded silently into an
  adjacent arithmetic step.
- Summing five line items is **one** step, not five. The operation is "sum these
  inputs", and it has one checkable value.
- Do not pad a chain to reach depth 4. Depth is a property of the question, and
  the per-depth breakdown is only informative if depth means the same thing
  across annotators.

Worked shape of a depth-3 item: convert the prior-year figure from lakh to
crore, subtract prior from current, express the difference as a percentage of
prior.

## 4. Restated figures

Indian annual reports routinely restate the prior year, after Ind AS
transitions, demergers, or reclassification of a segment.

Rule: **the figure is whatever the document being cited prints, in the column it
prints it in.** If the FY2023 report shows FY2022 revenue restated to 980 crore
while the FY2022 report showed 1,010 crore, an item anchored on the FY2023
report uses 980, sets `restated: true`, and carries a `restatement_note` naming
the restatement (for example: "FY2022 comparatives restated in the FY2023 report
following the demerger of the retail segment, note 41").

- Never mix a restated comparative with an as-originally-reported figure from a
  different document inside one item. That is two documents, and every item is
  single-document.
- If a question would have a different answer depending on which vintage you
  read, and the question text does not pin the vintage, the item is ambiguous:
  drop it (section 6).
- `restated: true` with no note is a schema error. The note is what a
  disagreeing reviewer needs in order to adjudicate.

## 5. FY vs CY, and units

- `FY2023` = year ended 31 March 2023. A company reporting to 31 December uses
  `CY`. Never silently map one onto the other; if an item needs both, that is a
  `convert` step and a unit trap.
- Indian filings use lakh (1e5) and crore (1e7); the same document may print a
  segment table in lakh and the P&L in crore. Record each figure with the unit
  of *its own* table. Mixed printed units force `unit_trap = true`.
- Million and billion appear in the same report when there is a US listing or an
  investor-deck section. Treat them as ordinary units, but note that
  1 crore = 10 million is the conversion models most often get wrong, which
  makes such items valuable.
- Rounding: use the figure as printed. Do not recover a "truer" number from a
  more precise table elsewhere in the document. If two tables in one report
  disagree, the item is ambiguous (section 6) unless the question names a table.

## 6. When to drop rather than resolve

Drop the item. Do not adjudicate, do not pick the more reasonable reading, do
not add a clarifying clause to rescue a question you have already invested in.
An ambiguous item costs the benchmark more than a missing one does.

Drop when:

1. Two readings of the question give different correct answers.
2. Consolidated vs standalone is not pinned and the two differ materially.
3. The figure exists in two places in the document with different values and the
   question does not name a table or note.
4. The chain needs a figure that is only available as an image.
5. The answer depends on a convention the document does not state (for example
   whether "revenue" includes other income).
6. You cannot write the chain without a step whose value you are not confident
   in to the item's own tolerance.

Log drops in `data/drops.jsonl` with a reason. The drop rate per sector is a
reported number: a sector with an unusually high drop rate is a finding about
the corpus, not noise to hide.

## 7. What must never happen

1. **The answer must not be derivable from the question and metadata alone.**
   No stating an intermediate value in the question, no "given that revenue rose
   by 200 crore". The schema has a literal-substring tripwire, but the real
   check is `scripts/oracle_ceiling.py`, which tries to score without reading the
   document. If it beats chance, the benchmark is broken.
2. **No item is authored from a synthetic or reconstructed document.** Real
   published reports only.
3. **No decoy figures.** Every figure listed must be consumed by a step,
   otherwise the retrieval axis is unscoreable. Enforced by the schema.
4. **The final answer must be the last step**, not an independently computed
   number. Otherwise two cancelling errors reach the right answer and the
   decomposition is decorative.
5. **Do not author items outside the split the CLI drew for you.** The CLI
   restricts the pool deliberately; drawing from anywhere else breaks the
   sampling frame.

## 8. Self-agreement protocol

Before an item is published, re-derive it from the PDF at least 24 hours later
without looking at the recorded chain. Disagreement on any step value or on a
page anchor means drop or rewrite, never patch. Report the self-agreement rate
in the README. A rate below 90% means these guidelines are underspecified, not
that the annotator was careless.

## 9. Deliberate divergences from indic-reg-bench

| Divergence | Why |
|---|---|
| Gold is a *chain*, not a label. | Four-axis decomposition needs per-step gold; a single label cannot support it. |
| `unit_trap` is derived and machine-checked, not annotator-asserted. | In indic-reg-bench the trap taxonomy is documentation the annotator applies by hand. Here the trap defines a separately reported subset score, so an inconsistent flag would corrupt a headline number. |
| No abstention task. | indic-reg-bench's T4 tests "no penalty imposed" as a label. Arithmetic has no equivalent well-formed null answer; an unanswerable item is dropped (section 6) rather than becoming an item. |
| Single-document items only. | indic-reg-bench allows cross-order aggregation. Cross-document arithmetic conflates retrieval failure with document-selection failure, which the retrieval axis could then not separate. |
| Tolerance is part of the item. | indic-reg-bench's numeric task uses one global tolerance. Ratios and rupee crores cannot share one, so tolerance is per item and its mode is schema-enforced. |
| `page` is the PDF index, not the printed folio. | Annual reports have unnumbered front matter; a printed folio is not addressable by a harness. |
