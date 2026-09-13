"""Render docs/corpus-by-sector.png from data/corpus.jsonl.

    python scripts/make_readme_chart.py
"""

import json
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]  # fixed categorical order

docs = [json.loads(line) for line in (ROOT / "data" / "corpus.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()]
counts = Counter((d["sector"], d["fiscal_year"]) for d in docs)
years = sorted({d["fiscal_year"] for d in docs})
sectors = sorted({d["sector"] for d in docs}, key=lambda s: sum(counts[s, y] for y in years))
companies = len({d["company"] for d in docs})

plt.switch_backend("Agg")
fig, ax = plt.subplots(figsize=(10, 4.6), dpi=120, facecolor="#fcfcfb")
ax.set_facecolor("#fcfcfb")
left = [0] * len(sectors)
for year, color in zip(years, COLORS):
    widths = [counts[s, year] for s in sectors]
    ax.barh([s.replace("_", " ") for s in sectors], widths, left=left, height=0.65,
            color=color, edgecolor="#fcfcfb", lw=2, label=year)
    left = [a + b for a, b in zip(left, widths)]
for y, total in enumerate(left):
    ax.text(total + 0.1, y, str(total), va="center", fontsize=8, color="#52514e")
ax.set_title(f"Corpus: {len(docs)} annual reports from {companies} companies, by sector and fiscal year",
             loc="left", color="#0b0b0b", fontsize=11)
ax.set_xlabel("documents", color="#52514e", fontsize=9)
ax.tick_params(colors="#52514e", labelsize=9, length=0)
ax.grid(axis="x", color="#e5e4e0", lw=0.8)
ax.set_axisbelow(True)
for side in ("top", "right", "left", "bottom"):
    ax.spines[side].set_visible(False)
ax.legend(frameon=False, loc="lower right", fontsize=9, labelcolor="#52514e")
fig.tight_layout()

out = ROOT / "docs" / "corpus-by-sector.png"
fig.savefig(out, facecolor=fig.get_facecolor())
print(f"wrote {out}")
