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
from .schema import Item
from .scoring import Prediction

PROMPT = """You are reading an Indian annual report. Answer the question using ONLY figures
from the document, and show the decomposition.

Document: {doc_id}
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


def build_prompt(item: Item) -> str:
    return PROMPT.format(
        doc_id=item.doc_id,
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


def predict(item: Item, adapter: Adapter, cache: Cache | None = None) -> tuple[Prediction, str]:
    """Returns (prediction, note). An unparseable response yields an empty
    prediction, which scores zero on every axis -- the honest outcome."""
    prompt = build_prompt(item)
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


def run(items: list[Item], adapter: Adapter, cache_dir: str | Path | None = ".cache") -> dict[str, Prediction]:
    cache = Cache(cache_dir) if cache_dir else None
    out: dict[str, Prediction] = {}
    for i, item in enumerate(items, 1):
        pred, note = predict(item, adapter, cache)
        out[item.item_id] = pred
        print(f"[{i}/{len(items)}] {item.item_id} {note}")
    return out
