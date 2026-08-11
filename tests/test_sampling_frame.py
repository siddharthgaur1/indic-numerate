"""Guards against the bug that has shipped twice: slicing an ordered set.

An ORDER BY that sorted by month name alphabetically, and a newest-first fetcher
whose partial results produced two false published claims. Both were prefixes of
an ordered collection taken without reshuffling. This file fails if a consumer
does that again, and if the seed is ever stated twice.

Escape hatch, deliberately noisy: a slice of a collection that is *already* the
output of a seeded shuffle must carry the marker comment

    # sampling-frame: shuffled by <where>

on the same line. The marker is not a silence button -- it puts the claim in the
diff where a reviewer has to look at it.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from indic_numerate.rng import SEED, rng, shuffled, take

ROOT = Path(__file__).resolve().parents[1]
SOURCES = sorted(ROOT.glob("src/indic_numerate/*.py")) + sorted(ROOT.glob("scripts/*.py"))
MARKER = "sampling-frame:"

# Calls that produce a collection. A slice of one of these, or of a name bound
# to one, is a sample -- and therefore must be shuffled first.
COLLECTION_CALLS = {"list", "sorted", "draw", "read_sources", "load_corpus", "load_items", "iter_items"}
SAFE_CALLS = {"take", "shuffled"}


# --- the seed lives in exactly one place ----------------------------------


def test_seed_is_stated_once():
    """Every module imports SEED from indic_numerate.rng. A second literal is a
    second sampling frame, and the two will diverge."""
    offenders = []
    for path in SOURCES:
        if path.name == "rng.py":
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"\b(seed|SEED)\s*=\s*\d", line) or re.search(r"random\.seed\(", line):
                offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()}")
    assert not offenders, (
        "the seed must be stated once, in indic_numerate/rng.py, and imported everywhere:\n"
        + "\n".join(offenders)
    )


def test_no_module_constructs_its_own_rng():
    offenders = []
    for path in SOURCES:
        if path.name == "rng.py":
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"random\.(Random\(|shuffle\(|sample\(|choice\()", line):
                offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()}")
    assert not offenders, (
        "use indic_numerate.rng (shuffled/take/rng) rather than the random module directly:\n"
        + "\n".join(offenders)
    )


# --- no consumer slices an ordered collection ------------------------------


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
        return getattr(node.func, "id", None) or getattr(node.func, "attr", None)
    return None


class _SliceFinder(ast.NodeVisitor):
    def __init__(self, path: Path, lines: list[str]):
        self.path = path
        self.lines = lines
        self.hits: list[str] = []
        self.collections: set[str] = set()   # names bound to a collection
        self.shuffled_names: set[str] = set()  # names bound to a seeded shuffle

    def visit_Assign(self, node: ast.Assign) -> None:
        name = _call_name(node.value)
        targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if name in SAFE_CALLS:
            self.shuffled_names.update(targets)
        elif name in COLLECTION_CALLS or isinstance(node.value, (ast.ListComp, ast.List)):
            self.collections.update(targets)
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        if isinstance(node.slice, ast.Slice):
            base = node.value
            is_collection = (
                (isinstance(base, ast.Name) and base.id in self.collections)
                or (_call_name(base) in COLLECTION_CALLS)
                or isinstance(base, (ast.ListComp, ast.List))
            )
            already_shuffled = (
                (isinstance(base, ast.Name) and base.id in self.shuffled_names)
                or (_call_name(base) in SAFE_CALLS)
            )
            marked = MARKER in self.lines[node.lineno - 1]
            if is_collection and not already_shuffled and not marked:
                self.hits.append(f"{self.path.name}:{node.lineno}: slice of {ast.unparse(base)}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if getattr(node.func, "attr", None) == "islice" and MARKER not in self.lines[node.lineno - 1]:
            self.hits.append(f"{self.path.name}:{node.lineno}: islice (an early stop is a sample)")
        self.generic_visit(node)


def test_no_unseeded_slice_of_a_collection():
    """The load-bearing test. If it fails, do not silence it -- route the
    collection through indic_numerate.rng.take() first."""
    hits: list[str] = []
    for path in SOURCES:
        if path.name == "rng.py":
            continue
        src = path.read_text(encoding="utf-8")
        finder = _SliceFinder(path, src.splitlines())
        finder.visit(ast.parse(src))
        hits += finder.hits
    assert not hits, (
        "a prefix/limit/early stop was taken from an ordered collection without a seeded "
        "reshuffle. Use indic_numerate.rng.take(). Offenders:\n" + "\n".join(hits)
    )


def test_the_guard_actually_catches_a_violation(tmp_path):
    """A guard nobody has seen fail is a guard nobody knows works."""
    bad = tmp_path / "bad.py"
    bad.write_text("docs = load_corpus('x')\nfirst = docs[:10]\n", encoding="utf-8")
    finder = _SliceFinder(bad, bad.read_text(encoding="utf-8").splitlines())
    finder.visit(ast.parse(bad.read_text(encoding="utf-8")))
    assert finder.hits and "slice of docs" in finder.hits[0]


def test_the_guard_accepts_a_seeded_take(tmp_path):
    good = tmp_path / "good.py"
    good.write_text("docs = load_corpus('x')\nfirst = take(docs, 10)\n", encoding="utf-8")
    finder = _SliceFinder(good, good.read_text(encoding="utf-8").splitlines())
    finder.visit(ast.parse(good.read_text(encoding="utf-8")))
    assert not finder.hits


def test_the_marker_requires_an_explanation(tmp_path):
    marked = tmp_path / "marked.py"
    marked.write_text("docs = load_corpus('x')\nfirst = docs[:10]  # sampling-frame: shuffled upstream\n", encoding="utf-8")
    finder = _SliceFinder(marked, marked.read_text(encoding="utf-8").splitlines())
    finder.visit(ast.parse(marked.read_text(encoding="utf-8")))
    assert not finder.hits


def test_every_marker_in_the_repo_says_where_the_shuffle_happened():
    """The marker must name its shuffle. `# sampling-frame:` alone is a shrug."""
    vague = []
    for path in SOURCES:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if MARKER in line and len(line.split(MARKER, 1)[1].split()) < 3:
                vague.append(f"{path.relative_to(ROOT)}:{lineno}")
    assert not vague, "sampling-frame markers must name where the shuffle happened: " + ", ".join(vague)


# --- the RNG itself --------------------------------------------------------


def test_shuffle_is_deterministic():
    xs = list(range(50))
    assert shuffled(xs) == shuffled(xs)
    assert shuffled(xs) != xs  # 1/50! chance of a false failure


def test_salt_gives_independent_streams():
    xs = list(range(50))
    assert shuffled(xs, "a") != shuffled(xs, "b")
    assert shuffled(xs, "a") == shuffled(xs, "a")


def test_take_reshuffles_before_limiting():
    xs = list(range(100))
    first10 = take(xs, 10)
    assert len(first10) == 10
    assert first10 != xs[:10]
    assert take(xs, 10) == first10  # reproducible


def test_take_none_returns_everything_shuffled():
    xs = list(range(20))
    assert sorted(take(xs, None)) == xs


def test_seed_is_pinned():
    # A literal expectation, so a change of seed or of Random construction is
    # caught rather than silently reshuffling every published sample.
    assert SEED == 20240917
    assert rng("check").random() == rng("check").random()


@pytest.mark.parametrize("n", [0, 1, 5])
def test_take_edge_sizes(n):
    assert len(take(list(range(5)), n)) == n
