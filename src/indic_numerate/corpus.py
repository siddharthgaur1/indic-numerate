"""Corpus provenance: one record per fetched annual report.

Provenance is not optional metadata. A benchmark item is only checkable if a
third party can obtain the same bytes the annotator read, so every document
carries its source URL, fetch date, and SHA-256 of the file. Convention follows
nse-warehouse: hash the raw bytes, store the URL as fetched (no redirects
collapsed), keep the fetch date in UTC ISO-8601.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterator

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .schema import Sector, period_basis


class Document(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    doc_id: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    company: str = Field(min_length=2)
    sector: Sector
    fiscal_year: str
    source_url: str = Field(pattern=r"^https?://")
    fetched_at: str  # UTC ISO-8601
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    n_bytes: int = Field(gt=0)
    n_pages: int | None = None
    local_path: str | None = None
    split: str | None = None

    def model_post_init(self, _ctx) -> None:
        period_basis(self.fiscal_year)  # raises on non-canonical fiscal years


class CorpusError(ValueError):
    """Raised for a malformed or missing corpus index."""


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_corpus(path: str | Path) -> list[Document]:
    """Load data/corpus.jsonl. Never fabricates a document."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} not found. Run `python scripts/fetch_reports.py` to fetch the real "
            "annual reports listed in data/sources.csv. This repo never generates a "
            "stand-in document: a benchmark that can invent its own corpus cannot be falsified."
        )
    docs: list[Document] = []
    seen: set[str] = set()
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            doc = Document.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise CorpusError(f"{path}:{lineno}: invalid document record -- {exc}") from exc
        if doc.doc_id in seen:
            raise CorpusError(f"{path}:{lineno}: duplicate doc_id {doc.doc_id!r}")
        seen.add(doc.doc_id)
        docs.append(doc)
    if not docs:
        raise CorpusError(f"{path}: corpus index is empty; nothing has been fetched yet")
    return docs


def append(path: str | Path, doc: Document) -> None:
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(doc.model_dump_json() + "\n")


def iter_corpus(path: str | Path) -> Iterator[Document]:
    yield from load_corpus(path)


def verify(docs: list[Document], pdf_dir: str | Path) -> list[str]:
    """Re-hash local files against the index. Returns a list of complaints.

    Used by scripts/fetch_reports.py --verify and by anyone reproducing the
    benchmark who wants to know their PDFs are the ones the items were written
    against.
    """
    pdf_dir = Path(pdf_dir)
    problems = []
    for doc in docs:
        local = pdf_dir / f"{doc.doc_id}.pdf"
        if not local.is_file():
            problems.append(f"{doc.doc_id}: missing {local}")
            continue
        actual = sha256_file(local)
        if actual != doc.sha256:
            problems.append(
                f"{doc.doc_id}: hash mismatch -- index says {doc.sha256[:12]}..., "
                f"file is {actual[:12]}... (the publisher may have silently replaced the PDF)"
            )
    return problems
