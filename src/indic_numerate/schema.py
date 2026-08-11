"""Item schema for indic-numerate.

The four scoring axes (retrieval / units / intermediate / final) are only
meaningful if every item carries separable gold for each one. The validators
below are what make that enforceable rather than aspirational: an item that
cannot be scored on all four axes fails to parse.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MONETARY_UNITS = ("rupees", "thousand", "lakh", "crore", "million", "billion")
DIMENSIONLESS_UNITS = ("percent", "ratio", "days", "count")
Unit = Literal[
    "rupees", "thousand", "lakh", "crore", "million", "billion",
    "percent", "ratio", "days", "count",
]
Operation = Literal[
    "add", "subtract", "multiply", "divide", "percent_change", "ratio", "convert",
]
Sector = Literal[
    "banking", "nbfc", "it_services", "pharma", "fmcg", "auto", "metals",
    "energy", "telecom", "infrastructure", "insurance", "other",
]

PERIOD_RE = re.compile(r"^(FY|CY|Q[1-4]FY)(\d{4})$")
STEP_ID_RE = re.compile(r"^s(\d+)$")
FIG_ID_RE = re.compile(r"^f\d+$")


def period_basis(period: str) -> str:
    """'FY2023' -> 'FY'; 'CY2022' -> 'CY'; 'Q3FY2024' -> 'FY'."""
    m = PERIOD_RE.match(period)
    if m is None:
        raise ValueError(
            f"period {period!r} must look like FY2023, CY2022 or Q3FY2024"
        )
    return "CY" if m.group(1) == "CY" else "FY"


class SourceFigure(BaseModel):
    """One figure the model must retrieve, recorded exactly as the page prints it.

    `value_as_printed` and `unit_as_printed` are the retrieval gold; keeping them
    unnormalised is what lets the units axis be scored independently of retrieval.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    fig_id: str = Field(pattern=FIG_ID_RE.pattern)
    label: str = Field(min_length=3)
    value_as_printed: Decimal
    unit_as_printed: Unit
    page: int = Field(ge=1)
    section: str | None = None
    period: str
    restated: bool = False
    restatement_note: str | None = None

    @model_validator(mode="after")
    def _check(self) -> "SourceFigure":
        period_basis(self.period)  # raises on malformed period
        if self.restated and not self.restatement_note:
            raise ValueError(
                f"figure {self.fig_id}: restated=True requires restatement_note "
                "naming the report the figure was restated in (see docs/annotation-guidelines.md #4)"
            )
        return self


class Step(BaseModel):
    """One reasoning step. `inputs` are fig_ids and/or earlier step ids."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    step_id: str = Field(pattern=STEP_ID_RE.pattern)
    description: str = Field(min_length=5)
    operation: Operation
    inputs: list[str] = Field(min_length=1)
    value: Decimal
    unit: Unit


class Tolerance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["relative", "absolute"]
    value: Decimal = Field(gt=0)


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    item_id: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    question: str = Field(min_length=15)
    doc_id: str = Field(min_length=3)
    figures: list[SourceFigure] = Field(min_length=1)
    steps: list[Step] = Field(min_length=2)
    final_value: Decimal
    final_unit: Unit
    tolerance: Tolerance
    reasoning_depth: Literal[2, 3, 4]
    unit_trap: bool
    sector: Sector
    fiscal_year: str
    split: Literal["train", "test"] | None = None

    @model_validator(mode="after")
    def _check(self) -> "Item":
        me = f"item {self.item_id}"
        period_basis(self.fiscal_year)

        fig_ids = [f.fig_id for f in self.figures]
        if len(set(fig_ids)) != len(fig_ids):
            raise ValueError(f"{me}: duplicate fig_id in figures: {fig_ids}")

        # --- intermediate axis: the step chain must be a closed DAG ------------
        step_ids = [s.step_id for s in self.steps]
        if step_ids != [f"s{i}" for i in range(1, len(self.steps) + 1)]:
            raise ValueError(f"{me}: steps must be numbered s1..s{len(self.steps)}, got {step_ids}")
        seen: set[str] = set(fig_ids)
        used: set[str] = set()
        for s in self.steps:
            unknown = [i for i in s.inputs if i not in seen]
            if unknown:
                raise ValueError(
                    f"{me}: step {s.step_id} references unknown inputs {unknown}; "
                    f"inputs must be fig_ids or earlier step ids"
                )
            used.update(s.inputs)
            seen.add(s.step_id)
        orphans = sorted(set(fig_ids) - used)
        if orphans:
            raise ValueError(
                f"{me}: figures {orphans} are never used by a step. Decoy gold figures "
                "make the retrieval axis unscoreable -- drop them or add the step that uses them"
            )

        if self.reasoning_depth != len(self.steps):
            raise ValueError(
                f"{me}: reasoning_depth={self.reasoning_depth} but {len(self.steps)} steps "
                "are listed; depth is the step count, not an estimate"
            )

        # --- final axis: the last step IS the answer ---------------------------
        last = self.steps[-1]
        if last.value != self.final_value or last.unit != self.final_unit:
            raise ValueError(
                f"{me}: final answer {self.final_value} {self.final_unit} does not match "
                f"last step {last.step_id} ({last.value} {last.unit}). Two cancelling errors "
                "must not be able to reach the final answer off-chain"
            )

        # --- units axis: the trap flag is derived, never asserted --------------
        derived_trap = (
            len({f.unit_as_printed for f in self.figures}) > 1
            or any(s.operation == "convert" for s in self.steps)
            or len({period_basis(f.period) for f in self.figures}) > 1
        )
        if derived_trap != self.unit_trap:
            raise ValueError(
                f"{me}: unit_trap={self.unit_trap} but the item's figures and steps imply "
                f"{derived_trap} (mixed printed units, a convert step, or mixed FY/CY basis). "
                "Fix the flag or the item -- the unit-trap subset is reported separately"
            )

        # --- tolerance semantics (see README 'Tolerance') ---------------------
        if self.final_unit in DIMENSIONLESS_UNITS and self.tolerance.mode != "absolute":
            raise ValueError(
                f"{me}: final_unit={self.final_unit} is dimensionless, so tolerance must be "
                "absolute (relative tolerance on a near-zero ratio is meaningless)"
            )
        if self.final_unit in MONETARY_UNITS and self.tolerance.mode != "relative":
            raise ValueError(
                f"{me}: final_unit={self.final_unit} is monetary, so tolerance must be "
                "relative (an absolute rupee tolerance does not transfer across magnitudes)"
            )

        # --- anti-circularity: answer must not be readable off the question ---
        # ponytail: literal-substring check only, and blind to answers under 3
        # significant digits (a "20" would match a page number). This is a tripwire,
        # not the real defence -- scripts/oracle_ceiling.py is (see README).
        digits = str(abs(self.final_value))
        if "." in digits:
            digits = digits.rstrip("0").rstrip(".")
        if len(digits.replace(".", "")) >= 3 and digits in self.question.replace(",", ""):
            raise ValueError(
                f"{me}: the final answer {self.final_value} appears verbatim in the question. "
                "The item is circular; rewrite the question (docs/annotation-guidelines.md #7)"
            )
        return self
