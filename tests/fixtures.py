"""Structural fixture. NOT a benchmark item.

doc_id is deliberately non-existent and the figures are round invented numbers:
this exercises the validators only. Real items are authored by hand against real
annual reports via scripts/write_items.py.
"""

import copy

VALID = {
    "item_id": "fixture-001",
    "question": "By what percentage did the company's total revenue change over the two years shown?",
    "doc_id": "FIXTURE-NOT-A-REAL-DOCUMENT",
    "figures": [
        {"fig_id": "f1", "label": "Total revenue, current year", "value_as_printed": "1200",
         "unit_as_printed": "crore", "page": 84, "section": "P&L", "period": "FY2023"},
        {"fig_id": "f2", "label": "Total revenue, prior year", "value_as_printed": "1000",
         "unit_as_printed": "crore", "page": 84, "section": "P&L", "period": "FY2022"},
    ],
    "steps": [
        {"step_id": "s1", "description": "Change in revenue", "operation": "subtract",
         "inputs": ["f1", "f2"], "value": "200", "unit": "crore"},
        {"step_id": "s2", "description": "Change as a percentage of prior year",
         "operation": "percent_change", "inputs": ["s1", "f2"], "value": "20", "unit": "percent"},
    ],
    "final_value": "20",
    "final_unit": "percent",
    "tolerance": {"mode": "absolute", "value": "0.05"},
    "reasoning_depth": 2,
    "unit_trap": False,
    "sector": "it_services",
    "fiscal_year": "FY2023",
    "split": "train",
}


def item(**overrides):
    d = copy.deepcopy(VALID)
    d.update(overrides)
    return d
