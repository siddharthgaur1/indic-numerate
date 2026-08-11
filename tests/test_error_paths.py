"""Every raise site gets a test. This file covers the ones the other suites do
not: corpus provenance, the fetcher's inputs, and the oracle-ceiling attacks.

The rule this repo starts with: a raise without a test is a message nobody has
ever read, and the three surfaces an outside user touches (loader, unit
normaliser, submission validator) must name the offending input.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from fixtures import VALID, item
from indic_numerate.corpus import CorpusError, Document, load_corpus, sha256_file, verify
from indic_numerate.schema import Item

DOC = {
    "doc_id": "example-fy2023",
    "company": "Example Ltd",
    "sector": "pharma",
    "fiscal_year": "FY2023",
    "source_url": "https://example.invalid/ar.pdf",
    "fetched_at": "2026-01-01T00:00:00+00:00",
    "sha256": "a" * 64,
    "n_bytes": 12345,
}


def corpus_file(tmp_path, *rows):
    p = tmp_path / "corpus.jsonl"
    p.write_text("\n".join(r if isinstance(r, str) else json.dumps(r) for r in rows), encoding="utf-8")
    return p


# --- corpus ---------------------------------------------------------------


def test_load_corpus(tmp_path):
    docs = load_corpus(corpus_file(tmp_path, DOC))
    assert docs[0].company == "Example Ltd"


def test_missing_corpus_tells_you_what_to_run(tmp_path):
    with pytest.raises(FileNotFoundError) as e:
        load_corpus(tmp_path / "nope.jsonl")
    msg = str(e.value)
    assert "fetch_reports.py" in msg and "never generates a stand-in" in msg


def test_empty_corpus_rejected(tmp_path):
    with pytest.raises(CorpusError, match="corpus index is empty"):
        load_corpus(corpus_file(tmp_path, ""))


def test_corpus_bad_json_names_the_line(tmp_path):
    with pytest.raises(CorpusError, match=r"corpus\.jsonl:2:"):
        load_corpus(corpus_file(tmp_path, DOC, "{nope"))


def test_corpus_duplicate_doc_id(tmp_path):
    with pytest.raises(CorpusError, match="duplicate doc_id 'example-fy2023'"):
        load_corpus(corpus_file(tmp_path, DOC, DOC))


@pytest.mark.parametrize(
    "field,value",
    [
        ("sha256", "not-a-hash"),
        ("source_url", "ftp://example.invalid/ar.pdf"),
        ("n_bytes", 0),
        ("doc_id", "Example FY2023"),
        ("sector", "cryptocurrency"),
    ],
)
def test_corpus_field_validation(tmp_path, field, value):
    with pytest.raises(CorpusError, match="invalid document record"):
        load_corpus(corpus_file(tmp_path, {**DOC, field: value}))


def test_corpus_rejects_non_canonical_fiscal_year(tmp_path):
    with pytest.raises(CorpusError, match="invalid document record"):
        load_corpus(corpus_file(tmp_path, {**DOC, "fiscal_year": "2022-23"}))


def test_corpus_rejects_unknown_fields(tmp_path):
    with pytest.raises(CorpusError, match="invalid document record"):
        load_corpus(corpus_file(tmp_path, {**DOC, "confidence": 0.9}))


def test_verify_reports_a_missing_pdf(tmp_path):
    docs = load_corpus(corpus_file(tmp_path, DOC))
    problems = verify(docs, tmp_path / "pdfs")
    assert len(problems) == 1 and "missing" in problems[0]


def test_verify_reports_a_silently_replaced_pdf(tmp_path):
    pdfs = tmp_path / "pdfs"
    pdfs.mkdir()
    (pdfs / "example-fy2023.pdf").write_bytes(b"%PDF-1.4 different bytes")
    docs = load_corpus(corpus_file(tmp_path, DOC))
    problems = verify(docs, pdfs)
    assert len(problems) == 1 and "hash mismatch" in problems[0]


def test_verify_passes_on_matching_bytes(tmp_path):
    pdfs = tmp_path / "pdfs"
    pdfs.mkdir()
    path = pdfs / "example-fy2023.pdf"
    path.write_bytes(b"%PDF-1.4 the real thing")
    docs = load_corpus(corpus_file(tmp_path, {**DOC, "sha256": sha256_file(path)}))
    assert verify(docs, pdfs) == []


# --- the fetcher's inputs --------------------------------------------------


def test_fetcher_requires_a_sources_file(tmp_path, monkeypatch):
    import fetch_reports

    with pytest.raises(SystemExit) as e:
        fetch_reports.read_sources(tmp_path / "sources.csv")
    assert "columns" in str(e.value) and "nothing is invented" in str(e.value)


def test_fetcher_rejects_a_sources_file_missing_columns(tmp_path):
    import fetch_reports

    p = tmp_path / "sources.csv"
    p.write_text("doc_id,company\nx,Y\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="missing required column"):
        fetch_reports.read_sources(p)


def test_fetcher_rejects_an_empty_sources_file(tmp_path):
    import fetch_reports

    p = tmp_path / "sources.csv"
    p.write_text("doc_id,company,sector,fiscal_year,source_url\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="no rows"):
        fetch_reports.read_sources(p)


# --- the oracle ceiling ----------------------------------------------------


def test_oracle_detects_a_leaking_question():
    """The attack must actually fire on an item that leaks its answer, or the
    check is decorative."""
    import oracle_ceiling

    leaky = Item.model_validate(
        item(
            item_id="leaky-001",
            # The schema's tripwire only catches >=3 significant digits, so a
            # two-digit leak like this reaches the oracle -- which is the point
            # of having both.
            question="Revenue rose 20 percent year on year; what was the percentage growth?",
        )
    )
    guess = oracle_ceiling.attack_question_numbers([])
    assert guess(leaky) == Decimal("20")


def test_oracle_finds_nothing_in_a_clean_question():
    import oracle_ceiling

    clean = Item.model_validate(VALID)
    assert oracle_ceiling.attack_question_numbers([])(clean) is None


def test_oracle_train_prior_uses_the_train_answers():
    import oracle_ceiling

    train = [Item.model_validate(item(item_id=f"t-{i}")) for i in range(3)]
    assert oracle_ceiling.attack_train_prior(train)(train[0]) == Decimal("20")


def test_oracle_nearest_question_copies_a_similar_item():
    import oracle_ceiling

    train = [Item.model_validate(VALID)]
    probe = Item.model_validate(item(item_id="probe-1"))
    assert oracle_ceiling.attack_nearest_question(train)(probe) == Decimal("20")


def test_oracle_numbers_parses_indian_comma_grouping():
    import oracle_ceiling

    assert Decimal("1200") in oracle_ceiling.numbers_in("revenue of 1,200 crore")
