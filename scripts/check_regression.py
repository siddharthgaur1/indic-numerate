#!/usr/bin/env python
"""Fail if a model's scores drop below the recorded floor.

results/baseline_floor.json maps model name -> {axis: minimum acceptable score}.
Each run's results/<model>.json is compared against it. A drop beyond
--tolerance fails; an improvement is reported and the floor is NOT raised
automatically, because raising it silently would hide the next regression.

While there are no baselines, this exits 0 and says so. It never invents a
floor to compare against.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
FLOOR = RESULTS / "baseline_floor.json"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tolerance", type=float, default=0.02)
    args = ap.parse_args()

    if not FLOOR.is_file():
        print("no results/baseline_floor.json: nothing to regress from yet (this is not a pass)")
        return 0
    floors = json.loads(FLOOR.read_text(encoding="utf-8"))
    failures = []
    for model, axes in floors.items():
        path = RESULTS / f"{model}.json"
        if not path.is_file():
            failures.append(f"{model}: floor recorded but {path.name} is missing")
            continue
        actual = json.loads(path.read_text(encoding="utf-8"))
        for axis, floor in axes.items():
            got = actual["axes"].get(axis, actual.get(axis))
            if got is None:
                failures.append(f"{model}.{axis}: not present in results")
            elif got < floor - args.tolerance:
                failures.append(f"{model}.{axis}: {got:.3f} < floor {floor:.3f} (tolerance {args.tolerance})")
    for f in failures:
        print("REGRESSION", f, file=sys.stderr)
    print(f"{'FAIL' if failures else 'OK'}: {len(failures)} regression(s) against {FLOOR.name}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
