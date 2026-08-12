# Bugs that looked like results

Same file as in indic-reg-bench, same purpose: the failures worth writing down are
the ones that produced a number rather than an error. Each entry names the bug,
what it looked like, and the test in this repo that would now catch it.

## 1. A prefix of an ordered set, twice

Two separate incidents in earlier projects. One was an `ORDER BY` over a
month-name column, which sorts April before January and made "the first N" mean
"whatever month starts with A". The other was a newest-first fetcher whose partial
results were used as if they were a sample; two published claims rested on it.

Neither produced an error. Both produced a plausible number.

**Caught here by:** `tests/test_sampling_frame.py::test_no_unseeded_slice_of_a_collection`
— an AST check that fails on any slice of a collection that did not come through
`indic_numerate.rng.take`. The only escape is a `# sampling-frame:` or
`# not-a-sample:` comment that has to say why, so the claim lands in the diff.

**And by:** `tests/test_stratification.py::test_every_prefix_of_the_authoring_pool_covers_multiple_strata`
— stratification over the population is not the property that matters; the prefix
someone actually uses is.

## 2. Synthetic fallback made a project unfalsifiable

A loader that generated a substitute when a document was missing. Everything ran.
Nothing measured anything, and there was no failure to notice.

**Caught here by:** the loader and the corpus index having no fallback path at all.
`tests/test_loader.py::test_missing_file_names_path_and_refuses_to_synthesise` and
`tests/test_error_paths.py::test_missing_corpus_tells_you_what_to_run` assert on
the refusal, so removing it breaks the suite.

## 3. A metric that could not distinguish skill from luck

Scoring only the final answer means a chain with two cancelling errors is
indistinguishable from a correct one. This is the reason the benchmark exists, and
it would have been easy to build the four axes as documentation rather than as
constraints.

**Caught here by:** `tests/test_scoring.py::test_cancelling_errors_do_not_score_correct`,
and by the schema rejecting any item whose final answer is not literally the last
step of its own chain.

## 4. The answer readable off the question

An item whose question states an intermediate value can be answered without the
document. A benchmark full of them scores retrieval systems on their arithmetic
priors.

**Caught here by:** a literal-substring tripwire in the schema (which only catches
answers with three or more significant digits, and says so), and by
`scripts/oracle_ceiling.py`, which must pass before any result is published.
`tests/test_error_paths.py::test_oracle_detects_a_leaking_question` checks the
oracle actually fires, because a circularity check nobody has seen succeed is not
a check.

## 5. A document-level split that leaked the answers

The split was assigned per document, on the reasoning that two items from the
same annual report share pages and phrasing. That is true, and it is not enough.

`infy-fy2024` landed in train and `infy-fy2025` in test. But **an FY2025 annual
report prints the FY2024 figures as its comparative column** — so the "unseen"
test document contained the training document's numbers verbatim, and the two
items' answers were 0.0228 percentage points apart on a 0.05 tolerance.

Nothing looked wrong. The split was seeded, stratified, and reproducible; the
stratification tests passed; no document appeared in both halves. The only thing
that caught it was `scripts/oracle_ceiling.py`, whose train-prior attack —
"answer every test item with the median train answer for its unit and depth" —
scored **0.167 against a chance baseline of 0.032, +0.135 above chance**, and
failed the gate.

That is the gate paying for itself. Without it, the first published number would
have been inflated by a leak nobody could see, on a benchmark whose entire selling
point is that it separates real ability from artefacts.

**Fix:** splits are now assigned per COMPANY (`indic_numerate/splits.py`), so every
report a company filed lands on the same side. Fiscal year stopped being a
stratification key as a consequence — a company has documents in both years and
moves as a unit — so only sector is split within, and `stratum_counts` still
reports the fiscal-year balance so it stays visible.

**Caught now by:** `tests/test_stratification.py::test_no_company_straddles_the_split`,
and by the oracle gate itself, which is run before anything is published.

**What was NOT done:** the tolerance was not tightened to make the hit go away.
0.05 percentage points is the right tolerance for a percentage answer; changing a
metric until a leak test passes is how a benchmark ends up measuring its own
tuning.

## 6. A README that drifted away from its own numbers

Caveats and counts that were true when written and quietly stopped being true.

**Caught here by:** `tests/test_readme.py` — the counts block is generated from
`data/` and compared, and each documented limitation is asserted present by name.
Deleting a caveat is a failing test, which is the point.
