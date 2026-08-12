#!/usr/bin/env python
"""Machine-drafted candidate items. NOT benchmark gold until a human reviews them.

Writes data/items_draft.jsonl. `data/items.jsonl` -- the file the loader, the
runner and the leaderboard read -- is only ever written by a person, either by
hand or by promoting a draft with scripts/promote_items.py after checking it
against the PDF.

Every figure below was read off the page named in its anchor. Every derived
value is computed here in Decimal and asserted against the chain, so a typo in a
gold value fails this script rather than silently becoming the answer key. What
this cannot check is whether the figure was read off the right row -- that is
what review is for, and it is why these are drafts.

    python scripts/draft_items.py            # write data/items_draft.jsonl
    python scripts/draft_items.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from indic_numerate.schema import Item  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DRAFTS = ROOT / "data" / "items_draft.jsonl"
DROPS = ROOT / "data" / "drops.jsonl"

D = Decimal


def q(value: Decimal, places: str = "0.0001") -> Decimal:
    return value.quantize(D(places), rounding=ROUND_HALF_UP)


def fig(fid, label, value, unit, page, section, period, restated=False, note=None):
    out = {"fig_id": fid, "label": label, "value_as_printed": str(value), "unit_as_printed": unit,
           "page": page, "section": section, "period": period, "restated": restated}
    if note:
        out["restatement_note"] = note
    return out


def step(sid, desc, op, inputs, value, unit):
    return {"step_id": sid, "description": desc, "operation": op, "inputs": inputs,
            "value": str(value), "unit": unit}


def build() -> list[dict]:
    items: list[dict] = []

    # ---------------------------------------------------------------- infosys
    # infy-fy2024.pdf p273, Consolidated Statement of Profit and Loss, in Rs crore.
    # Note the page prints BOTH digit groupings: 153,670 (Western) and 1,58,381
    # (Indian) in the same table.
    ti24, ti23 = D("158381"), D("149468")
    diff = ti24 - ti23
    growth = q(diff / ti23 * 100)
    items.append(dict(
        item_id="infy-fy2024-d01",
        question=("In Infosys's consolidated statement of profit and loss for the year ended "
                  "31 March 2024, by what percentage did total income change from the previous year?"),
        doc_id="infy-fy2024",
        figures=[
            fig("f1", "Total income, year ended 31 March 2024", ti24, "crore", 273,
                "Consolidated Statement of Profit and Loss", "FY2024"),
            fig("f2", "Total income, year ended 31 March 2023 (comparative)", ti23, "crore", 273,
                "Consolidated Statement of Profit and Loss", "FY2023"),
        ],
        steps=[
            step("s1", "Change in total income over the prior year", "subtract", ["f1", "f2"], diff, "crore"),
            step("s2", "Change as a percentage of the prior year", "percent_change", ["s1", "f2"], growth, "percent"),
        ],
        final_value=str(growth), final_unit="percent",
        tolerance={"mode": "absolute", "value": "0.05"},
        reasoning_depth=2, unit_trap=False, sector="it_services", fiscal_year="FY2024", split="train",
    ))

    # Margin movement in percentage points: four steps, and the last one is a
    # unit conversion, so this is a unit-trap item.
    p24, p23 = D("26248"), D("24108")
    m24 = p24 / ti24
    m23 = p23 / ti23
    dm = m24 - m23
    items.append(dict(
        item_id="infy-fy2024-d02",
        question=("Using Infosys's consolidated statement of profit and loss for the year ended "
                  "31 March 2024, by how many percentage points did profit for the year as a share "
                  "of total income move against the comparative year?"),
        doc_id="infy-fy2024",
        figures=[
            fig("f1", "Profit for the year, year ended 31 March 2024", p24, "crore", 273,
                "Consolidated Statement of Profit and Loss", "FY2024"),
            fig("f2", "Total income, year ended 31 March 2024", ti24, "crore", 273,
                "Consolidated Statement of Profit and Loss", "FY2024"),
            fig("f3", "Profit for the year, year ended 31 March 2023 (comparative)", p23, "crore", 273,
                "Consolidated Statement of Profit and Loss", "FY2023"),
            fig("f4", "Total income, year ended 31 March 2023 (comparative)", ti23, "crore", 273,
                "Consolidated Statement of Profit and Loss", "FY2023"),
        ],
        steps=[
            step("s1", "Profit as a share of total income, current year", "divide", ["f1", "f2"], q(m24, "0.000001"), "ratio"),
            step("s2", "Profit as a share of total income, comparative year", "divide", ["f3", "f4"], q(m23, "0.000001"), "ratio"),
            step("s3", "Movement in the share, as a ratio", "subtract", ["s1", "s2"], q(dm, "0.000001"), "ratio"),
            step("s4", "Movement expressed in percentage points", "convert", ["s3"], q(dm * 100), "percent"),
        ],
        final_value=str(q(dm * 100)), final_unit="percent",
        tolerance={"mode": "absolute", "value": "0.02"},
        reasoning_depth=4, unit_trap=True, sector="it_services", fiscal_year="FY2024", split="train",
    ))

    # ------------------------------------------------------------- tata steel
    # tatasteel-fy2025.pdf p408, Consolidated Statement of Profit and Loss, Rs crore.
    r25, r24 = D("218542.51"), D("229170.78")
    dr = r25 - r24
    items.append(dict(
        item_id="tatasteel-fy2025-d01",
        question=("In Tata Steel's consolidated statement of profit and loss for the year ended "
                  "31 March 2025, by what percentage did revenue from operations change against "
                  "the comparative year?"),
        doc_id="tatasteel-fy2025",
        figures=[
            fig("f1", "Revenue from operations, year ended 31 March 2025", r25, "crore", 408,
                "Consolidated Statement of Profit and Loss", "FY2025"),
            fig("f2", "Revenue from operations, year ended 31 March 2024 (comparative)", r24, "crore", 408,
                "Consolidated Statement of Profit and Loss", "FY2024"),
        ],
        steps=[
            step("s1", "Change in revenue from operations", "subtract", ["f1", "f2"], q(dr, "0.01"), "crore"),
            step("s2", "Change as a percentage of the comparative year", "percent_change", ["s1", "f2"],
                 q(dr / r24 * 100), "percent"),
        ],
        final_value=str(q(dr / r24 * 100)), final_unit="percent",
        tolerance={"mode": "absolute", "value": "0.05"},
        reasoning_depth=2, unit_trap=False, sector="metals", fiscal_year="FY2025", split="train",
    ))

    tinc, texp = D("220083.04"), D("211006.34")
    op = tinc - texp
    items.append(dict(
        item_id="tatasteel-fy2025-d02",
        question=("From Tata Steel's consolidated statement of profit and loss for the year ended "
                  "31 March 2025, what was the excess of total income over total expenses, expressed "
                  "as a percentage of total income?"),
        doc_id="tatasteel-fy2025",
        figures=[
            fig("f1", "Total income, year ended 31 March 2025", tinc, "crore", 408,
                "Consolidated Statement of Profit and Loss", "FY2025"),
            fig("f2", "Total expenses, year ended 31 March 2025", texp, "crore", 408,
                "Consolidated Statement of Profit and Loss", "FY2025"),
        ],
        steps=[
            step("s1", "Total income less total expenses", "subtract", ["f1", "f2"], q(op, "0.01"), "crore"),
            step("s2", "That excess as a share of total income", "divide", ["s1", "f1"], q(op / tinc, "0.000001"), "ratio"),
            step("s3", "Share expressed as a percentage", "convert", ["s2"], q(op / tinc * 100), "percent"),
        ],
        final_value=str(q(op / tinc * 100)), final_unit="percent",
        tolerance={"mode": "absolute", "value": "0.02"},
        reasoning_depth=3, unit_trap=True, sector="metals", fiscal_year="FY2025", split="train",
    ))

    # ----------------------------------------------------------------- maruti
    # maruti-fy2025.pdf p216, Consolidated Statement of Profit and Loss, in Rs MILLION.
    # The answer is asked for in crore, so the chain must cross units.
    mti, mrev = D("1579352"), D("1529130")
    other = mti - mrev
    items.append(dict(
        item_id="maruti-fy2025-d01",
        question=("Maruti Suzuki's consolidated statement of profit and loss for the year ended "
                  "31 March 2025 reports total income and revenue from operations. What was other "
                  "income for that year, in Rs crore?"),
        doc_id="maruti-fy2025",
        figures=[
            fig("f1", "Total Income (I+II), year ended 31 March 2025", mti, "million", 216,
                "Consolidated Statement of Profit and Loss", "FY2025"),
            fig("f2", "Revenue from operations, year ended 31 March 2025", mrev, "million", 216,
                "Consolidated Statement of Profit and Loss", "FY2025"),
        ],
        steps=[
            step("s1", "Total income less revenue from operations", "subtract", ["f1", "f2"], other, "million"),
            step("s2", "Converted from million to crore", "convert", ["s1"], q(other / 10, "0.01"), "crore"),
        ],
        final_value=str(q(other / 10, "0.01")), final_unit="crore",
        tolerance={"mode": "relative", "value": "0.005"},
        reasoning_depth=2, unit_trap=True, sector="auto", fiscal_year="FY2025", split="train",
    ))

    # ------------------------------------------------------------------ nestle
    # nestleind-fy2025.pdf p153, in Rs MILLION. The comparative column is a
    # FIFTEEN-month period, so no year-on-year item may be built here; this item
    # stays inside the FY2025 column. See data/drops.jsonl.
    nti, nrev = D("202604.2"), D("202015.6")
    nother = nti - nrev
    items.append(dict(
        item_id="nestleind-fy2025-d01",
        question=("Nestle India's consolidated statement of profit and loss for the year ended "
                  "31 March 2025 reports total income and revenue from operations. What was other "
                  "income for that year, in Rs crore?"),
        doc_id="nestleind-fy2025",
        figures=[
            fig("f1", "Total Income, financial year ended 31 March 2025", nti, "million", 153,
                "Consolidated Statement of Profit and Loss", "FY2025"),
            fig("f2", "Revenue from operations, financial year ended 31 March 2025", nrev, "million", 153,
                "Consolidated Statement of Profit and Loss", "FY2025"),
        ],
        steps=[
            step("s1", "Total income less revenue from operations", "subtract", ["f1", "f2"], q(nother, "0.1"), "million"),
            step("s2", "Converted from million to crore", "convert", ["s1"], q(nother / 10, "0.001"), "crore"),
        ],
        final_value=str(q(nother / 10, "0.001")), final_unit="crore",
        tolerance={"mode": "relative", "value": "0.005"},
        reasoning_depth=2, unit_trap=True, sector="fmcg", fiscal_year="FY2025", split="train",
    ))

    # ------------------------------------------------------- infosys FY2025 (test)
    # infy-fy2025.pdf p197 is in the STANDALONE section (pages 182-264); the
    # consolidated section begins at p265. The question pins the scope.
    sr25, sr24 = D("136592"), D("128933")
    sdiff = sr25 - sr24
    items.append(dict(
        item_id="infy-fy2025-d01",
        question=("In Infosys's standalone statement of profit and loss for the year ended "
                  "31 March 2025, by what percentage did revenue from operations grow against "
                  "the comparative year?"),
        doc_id="infy-fy2025",
        figures=[
            fig("f1", "Revenue from operations, year ended 31 March 2025 (standalone)", sr25, "crore", 197,
                "Standalone Statement of Profit and Loss", "FY2025"),
            fig("f2", "Revenue from operations, year ended 31 March 2024 (standalone comparative)", sr24,
                "crore", 197, "Standalone Statement of Profit and Loss", "FY2024"),
        ],
        steps=[
            step("s1", "Growth in revenue from operations", "subtract", ["f1", "f2"], sdiff, "crore"),
            step("s2", "Growth as a percentage of the comparative year", "percent_change", ["s1", "f2"],
                 q(sdiff / sr24 * 100), "percent"),
        ],
        final_value=str(q(sdiff / sr24 * 100)), final_unit="percent",
        tolerance={"mode": "absolute", "value": "0.05"},
        reasoning_depth=2, unit_trap=False, sector="it_services", fiscal_year="FY2025", split="test",
    ))

    # ---------------------------------------------------------- reliance (test)
    # reliance-fy2025.pdf p127, Consolidated Statement of Profit and Loss, Rs crore.
    # Revenue from operations is Value of Sales & Services less GST recovered, and
    # the page prints all four figures, so the chain is checkable end to end.
    v25, g25, v24, g24 = D("1071174"), D("91038"), D("1000122"), D("85650")
    net25, net24 = v25 - g25, v24 - g24
    ndiff = net25 - net24
    items.append(dict(
        item_id="reliance-fy2025-d01",
        question=("Reliance Industries' consolidated statement of profit and loss for the year ended "
                  "31 March 2025 reports value of sales and services and the GST recovered on it. "
                  "Taking revenue as value of sales and services net of GST recovered, by what "
                  "percentage did it change against the comparative year?"),
        doc_id="reliance-fy2025",
        figures=[
            fig("f1", "Value of Sales & Services (Revenue), 2024-25", v25, "crore", 127,
                "Consolidated Statement of Profit and Loss", "FY2025"),
            fig("f2", "Less: GST Recovered, 2024-25", g25, "crore", 127,
                "Consolidated Statement of Profit and Loss", "FY2025"),
            fig("f3", "Value of Sales & Services (Revenue), 2023-24", v24, "crore", 127,
                "Consolidated Statement of Profit and Loss", "FY2024"),
            fig("f4", "Less: GST Recovered, 2023-24", g24, "crore", 127,
                "Consolidated Statement of Profit and Loss", "FY2024"),
        ],
        steps=[
            step("s1", "Sales and services net of GST, current year", "subtract", ["f1", "f2"], net25, "crore"),
            step("s2", "Sales and services net of GST, comparative year", "subtract", ["f3", "f4"], net24, "crore"),
            step("s3", "Change between the two years", "subtract", ["s1", "s2"], ndiff, "crore"),
            step("s4", "Change as a percentage of the comparative year", "percent_change", ["s3", "s2"],
                 q(ndiff / net24 * 100), "percent"),
        ],
        final_value=str(q(ndiff / net24 * 100)), final_unit="percent",
        tolerance={"mode": "absolute", "value": "0.05"},
        reasoning_depth=4, unit_trap=False, sector="energy", fiscal_year="FY2025", split="test",
    ))

    # --------------------------------------------------------------- HUL (test)
    # hindunilvr-fy2025.pdf p187, Consolidated Statement of Profit and Loss, Rs crores.
    h25, h24 = D("10649"), D("10277")
    hd = h25 - h24
    items.append(dict(
        item_id="hindunilvr-fy2025-d01",
        question=("In Hindustan Unilever's consolidated statement of profit and loss for the year "
                  "ended 31 March 2025, by what percentage did profit attributable to owners of the "
                  "company change against the comparative year?"),
        doc_id="hindunilvr-fy2025",
        figures=[
            fig("f1", "Profit attributable to owners of the Company, year ended 31 March 2025", h25,
                "crore", 187, "Consolidated Statement of Profit and Loss", "FY2025"),
            fig("f2", "Profit attributable to owners of the Company, year ended 31 March 2024", h24,
                "crore", 187, "Consolidated Statement of Profit and Loss", "FY2024"),
        ],
        steps=[
            step("s1", "Change in profit attributable to owners", "subtract", ["f1", "f2"], hd, "crore"),
            step("s2", "Change as a percentage of the comparative year", "percent_change", ["s1", "f2"],
                 q(hd / h24 * 100), "percent"),
        ],
        final_value=str(q(hd / h24 * 100)), final_unit="percent",
        tolerance={"mode": "absolute", "value": "0.05"},
        reasoning_depth=2, unit_trap=False, sector="fmcg", fiscal_year="FY2025", split="test",
    ))

    hti25, hti24 = D("64138"), D("62707")
    hm25, hm24 = h25 / hti25, h24 / hti24
    hdm = hm25 - hm24
    items.append(dict(
        item_id="hindunilvr-fy2025-d02",
        question=("Using Hindustan Unilever's consolidated statement of profit and loss for the year "
                  "ended 31 March 2025, by how many percentage points did profit attributable to "
                  "owners as a share of total income move against the comparative year?"),
        doc_id="hindunilvr-fy2025",
        figures=[
            fig("f1", "Profit attributable to owners of the Company, year ended 31 March 2025", h25,
                "crore", 187, "Consolidated Statement of Profit and Loss", "FY2025"),
            fig("f2", "TOTAL INCOME, year ended 31 March 2025", hti25, "crore", 187,
                "Consolidated Statement of Profit and Loss", "FY2025"),
            fig("f3", "Profit attributable to owners of the Company, year ended 31 March 2024", h24,
                "crore", 187, "Consolidated Statement of Profit and Loss", "FY2024"),
            fig("f4", "TOTAL INCOME, year ended 31 March 2024", hti24, "crore", 187,
                "Consolidated Statement of Profit and Loss", "FY2024"),
        ],
        steps=[
            step("s1", "Profit share of total income, current year", "divide", ["f1", "f2"], q(hm25, "0.000001"), "ratio"),
            step("s2", "Profit share of total income, comparative year", "divide", ["f3", "f4"], q(hm24, "0.000001"), "ratio"),
            step("s3", "Movement in the share, as a ratio", "subtract", ["s1", "s2"], q(hdm, "0.000001"), "ratio"),
            step("s4", "Movement expressed in percentage points", "convert", ["s3"], q(hdm * 100), "percent"),
        ],
        final_value=str(q(hdm * 100)), final_unit="percent",
        tolerance={"mode": "absolute", "value": "0.02"},
        reasoning_depth=4, unit_trap=True, sector="fmcg", fiscal_year="FY2025", split="test",
    ))

    # ------------------------------------------------------------ bharti airtel
    # bhartiartl-fy2025.pdf p201, Consolidated Statement of Profit and Loss,
    # "All amounts are in millions of Indian Rupee".
    ar25, ar24 = D("1729852"), D("1499824")
    adiff = ar25 - ar24
    items.append(dict(
        item_id="bhartiartl-fy2025-d01",
        question=("In Bharti Airtel's consolidated statement of profit and loss for the year ended "
                  "31 March 2025, by what percentage did revenue from operations grow against the "
                  "comparative year?"),
        doc_id="bhartiartl-fy2025",
        figures=[
            fig("f1", "Revenue from operations, year ended 31 March 2025", ar25, "million", 201,
                "Consolidated Statement of Profit and Loss", "FY2025"),
            fig("f2", "Revenue from operations, year ended 31 March 2024 (comparative)", ar24,
                "million", 201, "Consolidated Statement of Profit and Loss", "FY2024"),
        ],
        steps=[
            step("s1", "Growth in revenue from operations", "subtract", ["f1", "f2"], adiff, "million"),
            step("s2", "Growth as a percentage of the comparative year", "percent_change", ["s1", "f2"],
                 q(adiff / ar24 * 100), "percent"),
        ],
        final_value=str(q(adiff / ar24 * 100)), final_unit="percent",
        tolerance={"mode": "absolute", "value": "0.05"},
        reasoning_depth=2, unit_trap=False, sector="telecom", fiscal_year="FY2025", split="train",
    ))

    ati25 = D("1745589")
    aother = ati25 - ar25
    items.append(dict(
        item_id="bhartiartl-fy2025-d02",
        question=("Bharti Airtel's consolidated statement of profit and loss for the year ended "
                  "31 March 2025 reports revenue from operations and a total income figure beneath "
                  "it. What was other income for that year, in Rs crore?"),
        doc_id="bhartiartl-fy2025",
        figures=[
            fig("f1", "Total of income, year ended 31 March 2025", ati25, "million", 201,
                "Consolidated Statement of Profit and Loss", "FY2025"),
            fig("f2", "Revenue from operations, year ended 31 March 2025", ar25, "million", 201,
                "Consolidated Statement of Profit and Loss", "FY2025"),
        ],
        steps=[
            step("s1", "Total income less revenue from operations", "subtract", ["f1", "f2"], aother, "million"),
            step("s2", "Converted from million to crore", "convert", ["s1"], q(aother / 10, "0.01"), "crore"),
        ],
        final_value=str(q(aother / 10, "0.01")), final_unit="crore",
        tolerance={"mode": "relative", "value": "0.005"},
        reasoning_depth=2, unit_trap=True, sector="telecom", fiscal_year="FY2025", split="train",
    ))

    aexp = D("798260")
    aebitda = ati25 - aexp
    items.append(dict(
        item_id="bhartiartl-fy2025-d03",
        question=("From Bharti Airtel's consolidated statement of profit and loss for the year ended "
                  "31 March 2025, what was the excess of total income over the expenses subtotal "
                  "shown before depreciation, amortisation and finance costs, as a share of total "
                  "income? Give the answer as a ratio."),
        doc_id="bhartiartl-fy2025",
        figures=[
            fig("f1", "Total of income, year ended 31 March 2025", ati25, "million", 201,
                "Consolidated Statement of Profit and Loss", "FY2025"),
            fig("f2", "Expenses subtotal before depreciation, amortisation and finance costs, "
                      "year ended 31 March 2025", aexp, "million", 201,
                "Consolidated Statement of Profit and Loss", "FY2025"),
        ],
        steps=[
            step("s1", "Total income less that expenses subtotal", "subtract", ["f1", "f2"], aebitda, "million"),
            step("s2", "That excess as a share of total income", "divide", ["s1", "f1"],
                 q(aebitda / ati25, "0.000001"), "ratio"),
        ],
        final_value=str(q(aebitda / ati25, "0.000001")), final_unit="ratio",
        tolerance={"mode": "absolute", "value": "0.0005"},
        reasoning_depth=2, unit_trap=False, sector="telecom", fiscal_year="FY2025", split="train",
    ))

    # ---------------------------------------------------------- coal india (test)
    # coalindia-fy2025.pdf p219. The page heading says "STATEMENT OF PROFIT AND
    # LOSS - STANDALONE" in its own text, so the question pins standalone. This is
    # the holding company alone, where most income is dividend from subsidiaries.
    csales, cother_op = D("177.08"), D("1417.09")
    crev = csales + cother_op
    cti = D("18221.46")
    items.append(dict(
        item_id="coalindia-fy2025-d01",
        question=("In Coal India's standalone statement of profit and loss for the year ended "
                  "31 March 2025, what was revenue from operations (net of levies) as a share of "
                  "total income? Give the answer as a ratio."),
        doc_id="coalindia-fy2025",
        figures=[
            fig("f1", "Sales, year ended 31 March 2025 (standalone)", csales, "crore", 219,
                "Standalone Statement of Profit and Loss", "FY2025"),
            fig("f2", "Other Operating Revenue, year ended 31 March 2025 (standalone)", cother_op,
                "crore", 219, "Standalone Statement of Profit and Loss", "FY2025"),
            fig("f3", "Total income (I+II), year ended 31 March 2025 (standalone)", cti, "crore", 219,
                "Standalone Statement of Profit and Loss", "FY2025"),
        ],
        steps=[
            step("s1", "Revenue from operations as sales plus other operating revenue", "add",
                 ["f1", "f2"], q(crev, "0.01"), "crore"),
            step("s2", "Revenue from operations as a share of total income", "divide", ["s1", "f3"],
                 q(crev / cti, "0.000001"), "ratio"),
        ],
        final_value=str(q(crev / cti, "0.000001")), final_unit="ratio",
        tolerance={"mode": "absolute", "value": "0.0005"},
        reasoning_depth=2, unit_trap=False, sector="energy", fiscal_year="FY2025", split="test",
    ))

    cother = D("16627.29")
    items.append(dict(
        item_id="coalindia-fy2025-d02",
        question=("Using Coal India's standalone statement of profit and loss for the year ended "
                  "31 March 2025, what percentage of total income came from other income rather "
                  "than from operations?"),
        doc_id="coalindia-fy2025",
        figures=[
            fig("f1", "Other Income, year ended 31 March 2025 (standalone)", cother, "crore", 219,
                "Standalone Statement of Profit and Loss", "FY2025"),
            fig("f2", "Total income (I+II), year ended 31 March 2025 (standalone)", cti, "crore", 219,
                "Standalone Statement of Profit and Loss", "FY2025"),
        ],
        steps=[
            step("s1", "Other income as a share of total income", "divide", ["f1", "f2"],
                 q(cother / cti, "0.000001"), "ratio"),
            step("s2", "Share expressed as a percentage", "convert", ["s1"], q(cother / cti * 100), "percent"),
        ],
        final_value=str(q(cother / cti * 100)), final_unit="percent",
        tolerance={"mode": "absolute", "value": "0.02"},
        reasoning_depth=2, unit_trap=True, sector="energy", fiscal_year="FY2025", split="test",
    ))

    return items


DROP_LOG = [
    {
        "doc_id": "nestleind-fy2025",
        "page": 153,
        "attempted": "year-on-year growth in revenue from operations",
        "reason": ("the comparative column is a FIFTEEN-month period ended 31 March 2024 "
                   "(Nestle India moved from a calendar year to an April-March fiscal year), so a "
                   "year-on-year growth figure computed against it is not a like-for-like comparison "
                   "and the question would have no single defensible answer"),
        "rule": "docs/annotation-guidelines.md section 6.1 and section 5",
    },
    {
        "doc_id": "infy-fy2025",
        "page": 197,
        "attempted": "any item using 'the statement of profit and loss' without naming the scope",
        "reason": ("page 197 sits in the standalone section (pages 182-264) but its own heading says "
                   "only 'Statement of Profit and Loss'; the consolidated equivalent at page 265+ "
                   "carries different figures. Items from this document must pin the scope in the "
                   "question, which infy-fy2025-d01 does"),
        "rule": "docs/annotation-guidelines.md section 6.2",
    },
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    raw = build()
    items = [Item.model_validate(r) for r in raw]  # the schema is the first reviewer
    print(f"{len(items)} draft item(s) validated against the schema")
    for i in items:
        print(f"  {i.item_id:26s} {i.split:5s} depth={i.reasoning_depth} trap={str(i.unit_trap):5s} "
              f"{i.final_value} {i.final_unit}")

    if args.dry_run:
        print("--dry-run: nothing written")
        return 0

    DRAFTS.write_text("\n".join(i.model_dump_json() for i in items) + "\n", encoding="utf-8")
    DROPS.write_text("\n".join(json.dumps(d) for d in DROP_LOG) + "\n", encoding="utf-8")
    print(f"\nwrote {DRAFTS.relative_to(ROOT)} and {DROPS.relative_to(ROOT)}")
    print("These are DRAFTS. Promote them with scripts/promote_items.py only after checking "
          "each figure against the PDF page named in its anchor.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
