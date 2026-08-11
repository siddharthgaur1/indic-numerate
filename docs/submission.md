# Submitting to indic-numerate

Run the validator before you send anything:

```bash
python scripts/validate_submission.py my_submission.json
```

## Format

One JSON file. Predictions must cover **every** item in the test split — partial
submissions are rejected rather than scored over what was supplied, because a
system that answered only the items it found easy would otherwise top the board.

```json
{
  "model": "vendor/model-name",
  "model_version": "2026-01-31",
  "contact": "you@example.com",
  "open_weights": false,
  "notes": "optional: scaffolding, retrieval setup, anything the board should carry",
  "predictions": [
    {
      "item_id": "reliance-fy2023-01",
      "figures": {
        "f1": {"value": 1200, "unit": "crore"},
        "f2": {"value": 1000, "unit": "crore"}
      },
      "periods": {"f1": "FY2023", "f2": "FY2022"},
      "steps": {
        "s1": {"value": 200, "unit": "crore"},
        "s2": {"value": 20, "unit": "percent"}
      },
      "final_value": 20,
      "final_unit": "percent"
    }
  ]
}
```

## What each field is scored on

| field | axis |
|---|---|
| `figures[fid].value` | **retrieval** — the digits as the page prints them. Do not convert before reporting. |
| `figures[fid].unit` | **units** — the unit that makes your reported digits the right magnitude. |
| `periods[fid]` | **units** — only scored on unit-trap items. `FY2023`, `CY2022`, `Q3FY2024` and `2022-23` are all accepted spellings. |
| `steps[sid].value/unit` | **intermediate** — all steps except the last. |
| `final_value` / `final_unit` | **final** — compared in the gold unit, within the item's own tolerance. |

An item counts as correct only if all four axes are perfect. A right final answer
with a wrong chain is reported in the leaderboard's `cancel gap` column, not as a
correct item.

## Units

`rupees, thousand, lakh, crore, million, billion, percent, ratio, days, count`
(`bps` is accepted for percentages). Common spellings are normalised: `Rs. in
Lakhs`, `INR mn`, `cr`, `%`, `times`. An unrecognised unit is a validation error
naming the item and the field, not a silent zero.

## Rules

1. The test split is for evaluation. Do not train, fine-tune, or few-shot on test
   items; the train split exists for that.
2. Report the model version you actually ran. The leaderboard carries it.
3. Say what scaffolding you used in `notes`. Bare-model and
   retrieval-pipeline numbers are not comparable, and the board shows both.
4. Nothing in a submission may contain gold fields (`tolerance`,
   `reasoning_depth`, `unit_trap`, `value_as_printed`). The validator rejects them.

## Submitting

Open a PR adding your validated JSON file to `submissions/`, or open an issue with
it attached. The maintainer scores it with
`python scripts/run_eval.py --submission your_file.json` and the leaderboard is
regenerated from `results/`.
