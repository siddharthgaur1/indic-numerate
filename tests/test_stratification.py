"""Stratification must survive to the consumer, not just to the population.

A correctly stratified corpus means nothing if the pool someone actually draws
from is ordered by sector, or if the prefix they take is all one fiscal year.
These tests check the split builder, the authoring CLI's draw, the loader's
split filter, and the report -- every consumer downstream of the split.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from indic_numerate.corpus import Document
from indic_numerate.splits import assign_splits, stratum_counts, stratum_of

ROOT = Path(__file__).resolve().parents[1]
SECTORS = ["banking", "it_services", "pharma", "auto", "energy"]
YEARS = ["FY2021", "FY2022", "FY2023"]


def population(per_cell: int = 6) -> list[Document]:
    """A corpus in the worst realistic order: grouped by sector, then by year --
    exactly what a scraper that walks a sector index produces."""
    docs = []
    for sector in SECTORS:
        for year in YEARS:
            for k in range(per_cell):
                i = len(docs)
                docs.append(
                    Document(
                        doc_id=f"doc-{i:03d}",
                        company=f"Company {i}",
                        sector=sector,
                        fiscal_year=year,
                        source_url=f"https://example.invalid/{i}.pdf",
                        fetched_at="2026-01-01T00:00:00+00:00",
                        sha256="0" * 64,
                        n_bytes=1000 + i,
                    )
                )
    return docs


def runs(labels: list[str]) -> int:
    """Number of contiguous same-label runs. A grouped ordering has few."""
    return 1 + sum(a != b for a, b in zip(labels, labels[1:]))


# --- the split itself ------------------------------------------------------


def test_every_stratum_is_split_not_just_the_population():
    docs = population()
    splits = assign_splits(docs, 1 / 3)
    for cell in {stratum_of(d) for d in docs}:
        members = [d for d in docs if stratum_of(d) == cell]
        n_test = sum(splits[d.doc_id] == "test" for d in members)
        assert n_test == 2, f"stratum {cell} put {n_test}/6 in test, expected 2"


def test_split_is_deterministic():
    docs = population()
    assert assign_splits(docs) == assign_splits(docs)


def test_singleton_stratum_goes_to_train():
    """A one-document cell in test would make that cell's score a coin flip."""
    docs = population(per_cell=1)
    splits = assign_splits(docs)
    assert set(splits.values()) == {"train"}


def test_split_rejects_empty_corpus():
    with pytest.raises(ValueError, match="empty corpus"):
        assign_splits([])


@pytest.mark.parametrize("bad", [0, 1, -0.2, 1.5])
def test_split_rejects_impossible_fraction(bad):
    with pytest.raises(ValueError, match="strictly between 0 and 1"):
        assign_splits(population(), bad)


def test_adding_a_sector_does_not_reshuffle_existing_ones():
    """Salting per stratum means last year's split survives a corpus extension."""
    docs = population()
    before = assign_splits(docs)
    extra = Document(
        doc_id="doc-999", company="New Co", sector="telecom", fiscal_year="FY2023",
        source_url="https://example.invalid/999.pdf", fetched_at="2026-01-01T00:00:00+00:00",
        sha256="0" * 64, n_bytes=1,
    )
    after = assign_splits(docs + [extra])
    assert {k: v for k, v in after.items() if k != "doc-999"} == before


def test_stratum_counts_reports_both_keys():
    docs = population()
    counts = stratum_counts(docs, assign_splits(docs, 1 / 3))
    assert counts["sector"]["banking/test"] == 6  # 3 years x 2 test docs
    assert counts["fiscal_year"]["FY2023/train"] == 20  # 5 sectors x 4 train docs


# --- the consumer: the authoring pool --------------------------------------


def authoring_pool(tmp_path, split="train"):
    """Exercise scripts/write_items.draw against a temporary corpus."""
    import write_items

    docs = population()
    splits = assign_splits(docs)
    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text("\n".join(d.model_dump_json() for d in docs), encoding="utf-8")
    split_dir = tmp_path / "splits"
    split_dir.mkdir(exist_ok=True)
    for name in ("train", "test"):
        (split_dir / f"{name}_ids.json").write_text(
            json.dumps(sorted(k for k, v in splits.items() if v == name)), encoding="utf-8"
        )
    write_items.CORPUS = corpus
    write_items.SPLIT_DIR = split_dir
    write_items.ITEMS = tmp_path / "items.jsonl"
    return write_items.draw(split, per_doc=1), {d.doc_id: d for d in docs}, splits


def test_authoring_pool_is_restricted_to_its_split(tmp_path):
    pool, _, splits = authoring_pool(tmp_path, "train")
    assert pool and all(splits[d.doc_id] == "train" for d in pool)


def test_authoring_pool_is_not_in_corpus_order(tmp_path):
    """The corpus arrives grouped by sector. If the CLI handed that order to the
    annotator, the first 20 items would all be banking -- the exact bug that
    produced two false published claims."""
    pool, _, _ = authoring_pool(tmp_path)
    drawn = [d.sector for d in pool]
    grouped = sorted(drawn)
    assert runs(drawn) > 2 * runs(grouped), f"draw order looks grouped: {runs(drawn)} runs"


def test_every_prefix_of_the_authoring_pool_covers_multiple_strata(tmp_path):
    """It is the PREFIX people use. A prefix of 10 must not be one sector."""
    pool, _, _ = authoring_pool(tmp_path)
    for k in (5, 10, 20):
        prefix = pool[:k]  # sampling-frame: shuffled by draw() via rng.take
        assert len(Counter(d.sector for d in prefix)) >= 3, f"prefix of {k} spans too few sectors"
        assert len(Counter(d.fiscal_year for d in prefix)) >= 2, f"prefix of {k} spans too few years"


def test_authoring_pool_is_stable_across_sessions(tmp_path):
    """Resumability: stopping and restarting must not redraw."""
    first, _, _ = authoring_pool(tmp_path)
    second, _, _ = authoring_pool(tmp_path)
    assert [d.doc_id for d in first] == [d.doc_id for d in second]


def test_authored_documents_drop_out_without_disturbing_the_order(tmp_path):
    import write_items

    pool, _, _ = authoring_pool(tmp_path)
    done = {pool[0].doc_id, pool[3].doc_id}  # sampling-frame: shuffled by draw() via rng.take
    write_items.existing_counts = lambda: Counter({d: 1 for d in done})
    resumed = write_items.draw("train", per_doc=1)
    assert [d.doc_id for d in resumed] == [d.doc_id for d in pool if d.doc_id not in done]


# --- items must agree with their document ---------------------------------


def test_item_splits_match_their_documents():
    """The document-level split is authoritative. If a corpus change moves a
    document between splits, an item still claiming the old split would leak a
    training document into the test set -- silently, and only in one direction.
    """
    import json

    items_path = ROOT / "data" / "items.jsonl"
    splits_dir = ROOT / "data" / "splits"
    if not (items_path.is_file() and (splits_dir / "train_ids.json").is_file()):
        pytest.skip("no items or splits yet")

    train = set(json.loads((splits_dir / "train_ids.json").read_text(encoding="utf-8")))
    test = set(json.loads((splits_dir / "test_ids.json").read_text(encoding="utf-8")))
    mismatches = []
    for line in items_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        doc_split = "train" if item["doc_id"] in train else "test" if item["doc_id"] in test else None
        if doc_split is None:
            mismatches.append(f"{item['item_id']}: document {item['doc_id']} is in no split")
        elif doc_split != item["split"]:
            mismatches.append(
                f"{item['item_id']}: item says {item['split']}, document {item['doc_id']} is {doc_split}"
            )
    assert not mismatches, chr(10).join(mismatches)


def test_every_item_document_is_in_the_corpus_and_readable():
    """An item anchored on a document that does not open cannot be checked by
    anyone reproducing the benchmark."""
    import json

    items_path = ROOT / "data" / "items.jsonl"
    audit_path = ROOT / "data" / "corpus_audit.json"
    if not (items_path.is_file() and audit_path.is_file()):
        pytest.skip("no items or audit yet")
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    unusable = set(audit["unusable_doc_ids"])
    openable = {d["doc_id"] for d in audit["documents"] if d["opens"]}
    for line in items_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            assert item["doc_id"] in openable, f"{item['item_id']}: {item['doc_id']} does not open"
            assert item["doc_id"] not in unusable, f"{item['item_id']}: {item['doc_id']} is unusable"
