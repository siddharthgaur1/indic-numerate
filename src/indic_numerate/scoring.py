"""Four independent scorers, one per axis.

    retrieval    -- were the correct source figures located
    units        -- was lakh/crore/million and FY-vs-CY handled correctly
    intermediate -- are the intermediate values right
    final        -- is the final number right within tolerance

The axes are deliberately separable:

* `retrieval` scores the DIGITS a model reports for each gold figure, ignoring
  the unit entirely. A model that reads "1,200" off the right row scores the
  retrieval point even if it then calls it lakh.
* `units` scores whether the unit attached to those digits puts the figure at
  the right magnitude, plus whether the periods line up (FY vs CY) and whether
  the final unit is right. A model that read the wrong row but labelled it
  consistently still fails retrieval, and vice versa.

`item_correct` requires all four axes to be 1.0. A run whose final answer is
right by two cancelling errors will show final=1.0 with intermediate<1.0 and is
NOT counted correct. That is the point of the benchmark.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from .schema import Item
from .units import UnitError, convert, family, parse_unit, same_period, to_base

RETRIEVAL_RTOL = Decimal("1e-9")  # digits are digits; this is float-noise slack only


@dataclass(frozen=True)
class AxisScore:
    score: float          # 0.0 .. 1.0
    detail: str           # human-readable, shown in per-item reports
    n: int = 1            # denominator, for aggregation


@dataclass
class Prediction:
    """What an adapter must produce for one item.

    Deliberately close to the gold shape: a model that cannot say which figures
    it used cannot be scored on retrieval, and scoring it only on the final
    answer is precisely the failure this benchmark exists to fix.
    """

    item_id: str
    figures: dict[str, tuple[Decimal, str]] = field(default_factory=dict)  # fig_id -> (value, unit)
    steps: dict[str, tuple[Decimal, str]] = field(default_factory=dict)    # step_id -> (value, unit)
    periods: dict[str, str] = field(default_factory=dict)                  # fig_id -> period label
    final_value: Decimal | None = None
    final_unit: str | None = None
    raw: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "Prediction":
        """Parse a model's JSON.

        Deliberately lenient in two narrow, documented ways, because this
        benchmark measures arithmetic over documents and not a model's ability
        to hit a JSON shape:

        * a unit is normalised through `units.parse_unit`, so "%", "Rs. crore"
          and "mn" are the units they obviously are. An unrecognisable unit is
          kept verbatim so the scorer and the submission validator can still
          name it in an error.
        * `final_value` given as {"value": x, "unit": u} is unpacked, since that
          is the shape the rest of the payload uses and models copy it.

        The leniency stops there. A missing answer is missing, a wrong number is
        wrong, and nothing is inferred from prose.
        """
        def unit_of(raw) -> str:
            text = str(raw)
            try:
                return parse_unit(text)
            except UnitError:
                return text

        def pairs(key: str) -> dict[str, tuple[Decimal, str]]:
            out = {}
            for k, v in (d.get(key) or {}).items():
                try:
                    out[k] = (Decimal(str(v["value"])), unit_of(v["unit"]))
                except (KeyError, TypeError, InvalidOperation) as exc:
                    raise ValueError(
                        f"prediction for item {d.get('item_id')!r}: {key}[{k!r}] must be "
                        f'{{"value": <number>, "unit": <unit>}}, got {v!r}'
                    ) from exc
            return out

        fv = d.get("final_value")
        final_unit = d.get("final_unit")
        if isinstance(fv, dict) and "value" in fv:  # models copy the {value, unit} shape
            final_unit = final_unit or fv.get("unit")
            fv = fv["value"]
        try:
            final = None if fv is None else Decimal(str(fv))
        except InvalidOperation as exc:
            raise ValueError(
                f"prediction for item {d.get('item_id')!r}: final_value {fv!r} is not a number"
            ) from exc
        return cls(
            item_id=str(d["item_id"]),
            figures=pairs("figures"),
            periods={str(k): str(v) for k, v in (d.get("periods") or {}).items()},
            steps=pairs("steps"),
            final_value=final,
            final_unit=None if final_unit is None else unit_of(final_unit),
            raw=str(d.get("raw", "")),
        )


def _close(a: Decimal, b: Decimal, mode: str, tol: Decimal) -> bool:
    if mode == "absolute":
        return abs(a - b) <= tol
    if b == 0:
        return a == 0
    return abs(a - b) / abs(b) <= tol


def _same_magnitude(value: Decimal, unit: str, gold_value: Decimal, gold_unit: str) -> bool:
    """True if the (value, unit) pair denotes the same quantity as the gold pair."""
    try:
        if family(unit) != family(gold_unit):
            return False
        return to_base(value, unit) == to_base(gold_value, gold_unit)
    except UnitError:
        return False


# --------------------------------------------------------------------------
# axis 1: retrieval -- digits only, unit ignored
# --------------------------------------------------------------------------


def score_retrieval(item: Item, pred: Prediction) -> AxisScore:
    hits, misses = 0, []
    for fig in item.figures:
        got = pred.figures.get(fig.fig_id)
        if got is not None and _close(got[0], fig.value_as_printed, "relative", RETRIEVAL_RTOL):
            hits += 1
        else:
            misses.append(f"{fig.fig_id}(want {fig.value_as_printed}, got {got[0] if got else 'nothing'})")
    n = len(item.figures)
    return AxisScore(hits / n, "all figures located" if not misses else "missed " + ", ".join(misses), n)


# --------------------------------------------------------------------------
# axis 2: units -- magnitude and period handling
# --------------------------------------------------------------------------


def score_units(item: Item, pred: Prediction) -> AxisScore:
    """One check per gold figure (does the unit put it at the right magnitude)
    plus one for the final unit. Retrieval failures are not double-counted: a
    figure whose digits are wrong is skipped, not marked a unit error."""
    checks, hits, problems = 0, 0, []
    for fig in item.figures:
        got = pred.figures.get(fig.fig_id)
        if got is None or not _close(got[0], fig.value_as_printed, "relative", RETRIEVAL_RTOL):
            continue  # a retrieval miss; scored on that axis, not this one
        checks += 1
        if _same_magnitude(got[0], got[1], fig.value_as_printed, fig.unit_as_printed):
            hits += 1
        else:
            problems.append(f"{fig.fig_id}: reported {got[1]}, printed {fig.unit_as_printed}")

    # FY-vs-CY. Only scored on unit-trap items, where the item's own figures
    # mix bases or need a conversion: elsewhere there is nothing to get wrong,
    # and a check nobody can fail inflates the axis.
    if item.unit_trap:
        for fig in item.figures:
            checks += 1
            got_period = pred.periods.get(fig.fig_id)
            try:
                ok = got_period is not None and same_period(got_period, fig.period)
            except UnitError:
                ok = False
            if ok:
                hits += 1
            else:
                problems.append(f"{fig.fig_id}: period {got_period or 'not reported'}, gold {fig.period}")

    checks += 1
    if pred.final_unit is not None and _unit_compatible(pred.final_unit, item.final_unit):
        hits += 1
    else:
        problems.append(f"final unit: reported {pred.final_unit}, expected {item.final_unit}")

    return AxisScore(
        hits / checks,
        "units handled" if not problems else "; ".join(problems),
        checks,
    )


def _unit_compatible(got: str, want: str) -> bool:
    """Same family is enough for the final unit; the magnitude itself is scored
    by the final axis, which converts. percent vs ratio is a units failure only
    if the value was not converted with it -- that is the final axis's job."""
    try:
        return family(got) == family(want)
    except UnitError:
        return False


# --------------------------------------------------------------------------
# axis 3: intermediates
# --------------------------------------------------------------------------


def score_intermediate(item: Item, pred: Prediction) -> AxisScore:
    """All steps except the last. The last step IS the final answer and is
    scored there; counting it twice would let the final axis inflate this one."""
    golds = item.steps[:-1]
    if not golds:
        return AxisScore(1.0, "no intermediate steps (depth 2 with a single operation)", 0)
    hits, problems = 0, []
    for step in golds:
        got = pred.steps.get(step.step_id)
        if got is None:
            problems.append(f"{step.step_id}: not reported")
            continue
        try:
            # Compare in the GOLD unit, never in base: an absolute tolerance of
            # 0.05 on a percentage means 0.05 percentage points, and comparing
            # in base rupees/ratios would silently rescale it by 100.
            ok = _close(
                convert(got[0], got[1], step.unit),
                step.value,
                item.tolerance.mode,
                item.tolerance.value,
            )
        except UnitError:
            ok = False
        if ok:
            hits += 1
        else:
            problems.append(f"{step.step_id}: got {got[0]} {got[1]}, want {step.value} {step.unit}")
    return AxisScore(hits / len(golds), "intermediates correct" if not problems else "; ".join(problems), len(golds))


# --------------------------------------------------------------------------
# axis 4: final
# --------------------------------------------------------------------------


def score_final(item: Item, pred: Prediction) -> AxisScore:
    if pred.final_value is None or pred.final_unit is None:
        return AxisScore(0.0, "no final answer reported")
    try:
        if family(pred.final_unit) != family(item.final_unit):
            return AxisScore(0.0, f"final unit {pred.final_unit} is the wrong family for {item.final_unit}")
        got = convert(pred.final_value, pred.final_unit, item.final_unit)  # gold unit, see above
    except UnitError as exc:
        return AxisScore(0.0, f"final unit unusable: {exc}")
    ok = _close(got, item.final_value, item.tolerance.mode, item.tolerance.value)
    return AxisScore(
        1.0 if ok else 0.0,
        "final correct" if ok else (
            f"got {pred.final_value} {pred.final_unit}, want {item.final_value} {item.final_unit} "
            f"({item.tolerance.mode} tol {item.tolerance.value})"
        ),
    )


AXES = ("retrieval", "units", "intermediate", "final")


def score_item(item: Item, pred: Prediction) -> dict[str, AxisScore]:
    if pred.item_id != item.item_id:
        raise ValueError(
            f"prediction item_id {pred.item_id!r} does not match item {item.item_id!r}"
        )
    return {
        "retrieval": score_retrieval(item, pred),
        "units": score_units(item, pred),
        "intermediate": score_intermediate(item, pred),
        "final": score_final(item, pred),
    }


def item_correct(scores: dict[str, AxisScore]) -> bool:
    """All four axes perfect. A right answer reached through a wrong chain is
    not correct here, which is the entire contribution of this benchmark."""
    return all(scores[a].score == 1.0 for a in AXES)
