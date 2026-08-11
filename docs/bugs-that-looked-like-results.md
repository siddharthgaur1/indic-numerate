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

## 5. A README that drifted away from its own numbers

Caveats and counts that were true when written and quietly stopped being true.

**Caught here by:** `tests/test_readme.py` — the counts block is generated from
`data/` and compared, and each documented limitation is asserted present by name.
Deleting a caveat is a failing test, which is the point.
