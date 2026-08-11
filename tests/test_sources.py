"""The source list is built from a stated frame, and the mapping is testable.

The frame matters more than it looks: guessing PDF URLs off investor-relations
sites returns 403 for most large Indian issuers, so a corpus built that way is
stratified by bot policy. These tests pin the sector mapping and the rule that a
revised filing supersedes the original.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

import build_sources
from indic_numerate.schema import Sector
from indic_numerate.units import parse_period

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "data" / "sources.csv"


def test_every_mapped_sector_is_in_the_schema_vocabulary():
    """A sector the schema does not know would fail at load time, one document
    at a time, long after the source list was built."""
    allowed = set(Sector.__args__)
    mapped = set(build_sources.INDUSTRY_TO_SECTOR.values())
    mapped |= set(build_sources.FINANCIAL_OVERRIDES) | {"banking"}
    assert mapped <= allowed, f"unknown sector(s): {sorted(mapped - allowed)}"


@pytest.mark.parametrize(
    "symbol,industry,expected",
    [
        ("INFY", "Information Technology", "it_services"),
        ("SUNPHARMA", "Healthcare", "pharma"),
        ("TATASTEEL", "Metals & Mining", "metals"),
        ("RELIANCE", "Oil Gas & Consumable Fuels", "energy"),
        ("POWERGRID", "Power", "energy"),
        ("BHARTIARTL", "Telecommunication", "telecom"),
        ("TITAN", "Consumer Durables", "other"),
        ("SOMETHINGNEW", "Unlisted Novelty", "other"),
    ],
)
def test_industry_mapping(symbol, industry, expected):
    assert build_sources.sector_for(symbol, industry) == expected


def test_financial_services_is_split_by_hand():
    """The index lumps banks, NBFCs and insurers together; their statements do
    not. README limitation 8 records that this split is maintainer judgement."""
    assert build_sources.sector_for("HDFCBANK", "Financial Services") == "banking"
    assert build_sources.sector_for("BAJFINANCE", "Financial Services") == "nbfc"
    assert build_sources.sector_for("SBILIFE", "Financial Services") == "insurance"


def test_missing_industry_does_not_crash():
    assert build_sources.sector_for("X", "") == "other"
    assert build_sources.sector_for("X", None) == "other"


# --- the committed source list ---------------------------------------------


@pytest.mark.skipif(not SOURCES.is_file(), reason="no source list yet")
def test_committed_sources_are_well_formed():
    rows = list(csv.DictReader(SOURCES.open(encoding="utf-8-sig")))
    assert rows, "source list is empty"
    ids = [r["doc_id"] for r in rows]
    assert len(set(ids)) == len(ids), "duplicate doc_id in sources.csv"
    for r in rows:
        assert r["source_url"].startswith("https://"), r
        assert r["source_url"].lower().endswith(".pdf"), r
        assert r["sector"] in Sector.__args__, r
        assert parse_period(r["fiscal_year"]) == r["fiscal_year"], r


@pytest.mark.skipif(not SOURCES.is_file(), reason="no source list yet")
def test_committed_sources_span_the_strata():
    """One sector or one year would make stratification meaningless downstream."""
    rows = list(csv.DictReader(SOURCES.open(encoding="utf-8-sig")))
    assert len({r["sector"] for r in rows}) >= 5
    assert len({r["fiscal_year"] for r in rows}) >= 2


@pytest.mark.skipif(not SOURCES.is_file(), reason="no source list yet")
def test_one_report_per_company_year():
    """A revised filing supersedes the original rather than appearing twice; two
    rows for one company-year would put the same document in both splits."""
    rows = list(csv.DictReader(SOURCES.open(encoding="utf-8-sig")))
    seen = {(r["company"], r["fiscal_year"]) for r in rows}
    assert len(seen) == len(rows)
