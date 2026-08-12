"""Caveats are load-bearing: these tests fail when the README goes stale.

Two kinds of drift are caught here -- a documented number that no longer matches
the data, and a documented limitation that has been quietly deleted.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from indic_numerate.rng import SEED
from indic_numerate.stats import BEGIN, END, current_counts, render_block, replace_block

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")

# Each entry is a phrase that must survive in the README. Deleting a caveat is a
# regression; if one genuinely no longer applies, deleting it here is the change
# that has to be justified in review.
REQUIRED_CAVEATS = [
    "Single-document items only",
    "No OCR",
    "page anchors are PDF indices",
    "Reasoning depth is capped at 4 steps",
    "one valid decomposition, not the only one",
    "Single annotator",
    "a hash does not prove a document is usable",
    "Sector labels come from NSE's own industry column",
    "Restated figures follow the citing document",
    "Adapters are thin",
    "The corpus frame is one index, large-cap only",
    "Constituents are as of the fetch date",
    "Fiscal years are limited to FY2024",
    "only the latest submission is",
    "changes what `retrieval` means",
    "The test split is four items from two companies",
    "splits are assigned per **company**",
    "machine-drafted and have not been page-level human",
]


def test_generated_counts_match_the_data():
    """The number in the README is the number in data/, or this fails."""
    expected = render_block(current_counts(ROOT))
    start = README.index(BEGIN)
    end = README.index(END) + len(END)
    assert README[start:end] == expected, (
        "README counts are stale. Run `python scripts/update_readme.py`."
    )


def test_seed_in_readme_matches_the_code():
    assert str(SEED) in README, "the README quotes the seed; it must be the real one"


@pytest.mark.parametrize("caveat", REQUIRED_CAVEATS)
def test_caveat_still_present(caveat):
    assert caveat in README, f"documented limitation removed from the README: {caveat!r}"


def test_readme_does_not_claim_results_while_there_are_none():
    """Guards the specific failure mode of publishing numbers before the oracle
    ceiling has been run: while there are zero items, the README must say so."""
    if current_counts(ROOT)["items"] == 0:
        assert "is still empty" in README
        # and the leaderboard must carry no result rows
        board = (ROOT / "LEADERBOARD.md").read_text(encoding="utf-8")
        assert "_no results yet_" in board, (
            "there are no reviewed items, so the leaderboard must have no rows"
        )
        # any baseline that has been run must be labelled provisional
        if "baseline" in README.lower():
            assert "rovisional" in README


def test_decomposition_rationale_leads_the_readme():
    head = README[: README.index("## Corpus at a glance")]
    assert "decomposition" in head.lower()
    assert "retrieval" in head and "units" in head and "intermediate" in head


def test_replace_block_requires_the_markers():
    with pytest.raises(ValueError, match="missing the"):
        replace_block("no markers here", "x")


def test_replace_block_roundtrip():
    text = f"a\n{BEGIN}\nold\n{END}\nb"
    out = replace_block(text, f"{BEGIN}\nnew\n{END}")
    assert "new" in out and "old" not in out and out.startswith("a") and out.endswith("b")


def test_counts_survive_missing_data_files(tmp_path):
    """No data yet is zero, never an estimate and never a crash."""
    counts = current_counts(tmp_path)
    assert counts["documents"] == 0 and counts["items"] == 0 and counts["seed"] == SEED
