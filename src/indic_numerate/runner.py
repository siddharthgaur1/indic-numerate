"""Evaluation runner: prompt, cache, parse, score.

Caching is by (item_id, adapter name, adapter version, prompt hash). An
unchanged item and an unchanged model version are never re-called, so a rerun
after a scoring change costs nothing. Cache entries record the prompt hash, so
a changed prompt is a cache miss rather than a silent stale hit.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .adapters import Adapter
from .rng import take
from .schema import Item
from .scoring import Prediction

PROMPT = """You are reading an Indian annual report. Answer the question using ONLY figures
from the document, and show the decomposition.

Document: {doc_id}
{context}
Question: {question}

Report your answer as JSON with exactly this shape:
{{
  "figures": {{"f1": {{"value": <number as printed>, "unit": "<unit as printed>"}}, ...}},
  "periods": {{"f1": "FY2023", ...}},
  "steps": {{"s1": {{"value": <number>, "unit": "<unit>"}}, ...}},
  "final_value": <number>,
  "final_unit": "<unit>"
}}

There are {n_figures} source figures (f1..f{n_figures}) and {n_steps} steps (s1..s{n_steps}).
Units may be one of: rupees, thousand, lakh, crore, million, billion, percent, ratio, days, count.
Report each figure exactly as the page prints it -- do not convert it before reporting.
Output the JSON and nothing else."""


# --------------------------------------------------------------------------
# Document context
#
# Without the document a model can only recall a filing it memorised, which is
# not what this benchmark measures. How much document a model gets changes what
# the retrieval axis means, so the mode is explicit, recorded in the report, and
# never defaulted silently:
#
#   none        no document text. Diagnostic only -- scores are recall, not reading.
#   anchored    exactly the pages the item's figures cite. Retrieval becomes
#               "find the right row on the right page", an UPPER BOUND: the model
#               is handed the page a real system would have to locate.
#   distractors anchored pages plus N other pages from the same document, drawn
#               with the shared seed and presented in page order. The default.
#
# Scores from different modes are not comparable and the report says which was used.
# --------------------------------------------------------------------------

CONTEXT_MODES = ("none", "anchored", "distractors")


def document_pages(doc_id: str, pages: list[int], pdf_dir: str | Path) -> dict[int, str]:
    """Extract text for specific pages. Missing PDF raises; nothing is invented."""
    import pdfplumber

    path = Path(pdf_dir) / f"{doc_id}.pdf"
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} not found. Fetch the corpus with scripts/fetch_reports.py; the runner "
            "will not evaluate against a document it does not have."
        )
    out: dict[int, str] = {}
    with pdfplumber.open(path) as pdf:
        for page in pages:
            if 1 <= page <= len(pdf.pages):
                out[page] = pdf.pages[page - 1].extract_text() or ""
    return out


def build_context(item: Item, mode: str = "distractors", pdf_dir: str | Path = "data/pdfs",
                  n_distractors: int = 4) -> str:
    if mode not in CONTEXT_MODES:
        raise ValueError(f"unknown context mode {mode!r}; expected one of {list(CONTEXT_MODES)}")
    if mode == "none":
        return ""
    anchored = sorted({f.page for f in item.figures})
    pages = list(anchored)
    if mode == "distractors":
        import pdfplumber

        path = Path(pdf_dir) / f"{item.doc_id}.pdf"
        if not path.is_file():
            raise FileNotFoundError(
                f"{path} not found. Fetch the corpus with scripts/fetch_reports.py."
            )
        with pdfplumber.open(path) as pdf:
            total = len(pdf.pages)
        pool = [p for p in range(1, total + 1) if p not in set(anchored)]
        # Seeded shuffle before taking any: a window around the anchor would put
        # the answer in the middle of every prompt, which is its own leak.
        pages += take(pool, n_distractors, salt=f"context:{item.item_id}")
    chunks = document_pages(item.doc_id, sorted(pages), pdf_dir)
    body = "\n\n".join(f"--- page {p} ---\n{text}" for p, text in sorted(chunks.items()))
    return f"Document extract ({len(chunks)} pages, not necessarily contiguous):\n{body}\n"


def build_prompt(item: Item, context: str = "") -> str:
    return PROMPT.format(
        doc_id=item.doc_id,
        context=context,
        question=item.question,
        n_figures=len(item.figures),
        n_steps=len(item.steps),
    )


def cache_key(item: Item, adapter: Adapter, prompt: str) -> str:
    raw = f"{item.item_id}|{adapter.name}|{adapter.version}|{hashlib.sha256(prompt.encode()).hexdigest()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


class Cache:
    """One JSON file per (item, model version, prompt). Boring on purpose."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def get(self, key: str) -> str | None:
        path = self.root / f"{key}.json"
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))["response"]

    def put(self, key: str, item_id: str, model: str, response: str) -> None:
        (self.root / f"{key}.json").write_text(
            json.dumps({"item_id": item_id, "model": model, "response": response}),
            encoding="utf-8",
        )


def extract_json(text: str) -> dict:
    """Pull the JSON object out of a model response.

    Models wrap JSON in prose and fences. A parse failure is a zero score for
    that item, never a crash and never a retry loop that quietly costs money.
    """
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError(f"no JSON object in response (first 80 chars: {text[:80]!r})")
    return json.loads(text[start : end + 1])


def predict(item: Item, adapter: Adapter, cache: Cache | None = None,
            context_mode: str = "distractors", pdf_dir: str | Path = "data/pdfs") -> tuple[Prediction, str]:
    """Returns (prediction, note). An unparseable response yields an empty
    prediction, which scores zero on every axis -- the honest outcome."""
    prompt = build_prompt(item, build_context(item, context_mode, pdf_dir))
    key = cache_key(item, adapter, prompt)
    response = cache.get(key) if cache else None
    note = "cached" if response is not None else "called"
    if response is None:
        response = adapter.generate(prompt)
        if cache:
            cache.put(key, item.item_id, adapter.name, response)
    try:
        payload = extract_json(response)
    except (ValueError, json.JSONDecodeError) as exc:
        return Prediction(item_id=item.item_id, raw=response), f"unparseable: {exc}"
    payload["item_id"] = item.item_id
    try:
        pred = Prediction.from_dict(payload)
    except ValueError as exc:
        return Prediction(item_id=item.item_id, raw=response), f"malformed: {exc}"
    pred.raw = response
    return pred, note


def run(items: list[Item], adapter: Adapter, cache_dir: str | Path | None = ".cache",
        context_mode: str = "distractors", pdf_dir: str | Path = "data/pdfs") -> dict[str, Prediction]:
    cache = Cache(cache_dir) if cache_dir else None
    out: dict[str, Prediction] = {}
    for i, item in enumerate(items, 1):
        pred, note = predict(item, adapter, cache, context_mode, pdf_dir)
        out[item.item_id] = pred
        print(f"[{i}/{len(items)}] {item.item_id} {note}")
    return out
