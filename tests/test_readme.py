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
    "Published reports change",
    "Sector labels are assigned by the maintainer",
    "Restated figures follow the citing document",
    "Adapters are thin",
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
        assert "Status: pre-data" in README
        assert "Pending" in README or "pending" in README


def test_decomposition_rationale_leads_the_readme():
    head = README[:2000]
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
