"""No aggregate is ever computed over the person.

Grounded in the strongest citation available anywhere in the expert-grounding
set, because it is an authority publishing the limit of his own instrument: Anda,
Porter and Brown (2020) on the ACE questionnaire, which was built for population
research and not for individual screening, and Baldwin et al. (2021) measuring
AUC between 0.5 and 0.6 for 11 of 19 outcomes. A strong population signal can be
nearly useless as an individual classifier.

Per-artifact and per-run history stays unbounded and fully retained. What must
not exist, at any granularity including per-workspace and per-device keys, is a
quantity whose SUBJECT is the human rather than the work: rates, streaks, risk
bands, consistency indices, percentiles, trend lines, or trust scores.

This is a schema-shaped rule. It is cheap to assert now and expensive to
retrofit once receipts have accumulated, which is exactly why it is frozen in
Phase 0 rather than promised for later.
"""
import ast
from pathlib import Path

HARNESS = Path(__file__).resolve().parent.parent / "harness"

# Names whose subject is the human rather than the work. A field counting
# artifacts, tasks, oracle calls or tokens is fine. A field scoring a person is
# not.
FORBIDDEN_SUBSTRINGS = (
    "operator_score", "user_score", "operator_rate", "user_rate",
    "operator_accuracy", "user_accuracy", "operator_reliability",
    "user_reliability", "operator_percentile", "user_percentile",
    "operator_trend", "user_trend", "operator_streak", "user_streak",
    "streak", "days_since_last", "last_seen_at", "consistency_index",
    "risk_band", "risk_score", "trust_score", "reputation_score",
    "competence_score", "operator_karma", "user_karma",
)


def _docstring_nodes(tree) -> set:
    """The Constant nodes that are docstrings.

    Excluded from the scan, because a docstring is not a persisted or exported
    quantity and the guard is about quantities. Leaving them in gave the guard a
    false positive on the most useful sentence in the codebase: `why.py`'s
    docstring says it will never report "a rate, a streak, or a history of the
    operator", and the guard flagged the promise not to do the thing. Any module
    that documents this invariant would hit the same wall, which would push
    people toward deleting the documentation rather than keeping the property.
    """
    out = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None)
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            out.add(id(body[0].value))
    return out


def _named_things(path: Path):
    """Every identifier, attribute name, and non-docstring string literal in a
    module, with its line. String literals matter because a schema field name is
    usually a dict key, not a Python identifier."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    skip = _docstring_nodes(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            yield node.id, node.lineno
        elif isinstance(node, ast.Attribute):
            yield node.attr, node.lineno
        elif isinstance(node, ast.arg):
            yield node.arg, node.lineno
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in skip:
                yield node.value, node.lineno


def test_no_module_names_a_quantity_whose_subject_is_the_person():
    hits = []
    for p in sorted(HARNESS.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        if p.name == "test_no_aggregate_over_the_person.py":
            continue
        for name, lineno in _named_things(p):
            low = name.lower()
            for bad in FORBIDDEN_SUBSTRINGS:
                if bad in low:
                    hits.append(f"{p.name}:{lineno} {name!r} contains {bad!r}")
    assert hits == [], (
        "a persisted or exported quantity whose subject is the operator rather "
        "than the work:\n  " + "\n  ".join(hits))


def test_the_guard_still_catches_a_real_quantity(tmp_path):
    """Bounds the docstring exemption. Skipping docstrings must not skip a dict
    key, an identifier, or a string that is not the first statement of a scope."""
    mod = tmp_path / "leak.py"
    mod.write_text(
        '"""A docstring mentioning operator_streak must not trip the guard."""\n'
        'SCHEMA = {"trust_score": 0.9}\n'
        'def f(user_streak=None):\n'
        '    note = "reputation_score"\n'
        '    return note\n', encoding="utf-8")
    found = {n for n, _ in _named_things(mod)}
    assert "trust_score" in found            # a dict key
    assert "user_streak" in found            # an argument name
    assert "reputation_score" in found       # a plain string literal
    assert not any("docstring mentioning" in n for n in found)


def test_the_check_can_actually_fire(tmp_path):
    """A test that has never been seen to fail is not evidence. This proves the
    scanner catches a violation in a real module."""
    offender = tmp_path / "offender.py"
    offender.write_text(
        'def report():\n'
        '    return {"operator_score": 0.8, "streak": 5}\n',
        encoding="utf-8")
    found = []
    for name, lineno in _named_things(offender):
        low = name.lower()
        if any(bad in low for bad in FORBIDDEN_SUBSTRINGS):
            found.append(name)
    assert "operator_score" in found
    assert "streak" in found


def test_artifact_scoped_counters_are_explicitly_allowed(tmp_path):
    """The rule is about the SUBJECT of the quantity, not about counting. A
    denominator over artifacts is required by the design, so it must pass."""
    ok = tmp_path / "fine.py"
    ok.write_text(
        'def denominator():\n'
        '    return {"attempts": 8, "oracle_calls_consumed": 9, "hits": 1,\n'
        '            "n_undecided": 0, "n_excluded": 0, "tokens_out": 512}\n',
        encoding="utf-8")
    violations = []
    for name, lineno in _named_things(ok):
        low = name.lower()
        if any(bad in low for bad in FORBIDDEN_SUBSTRINGS):
            violations.append(name)
    assert violations == []


def test_no_trust_score_field_exists_anywhere_in_the_harness():
    """Called out separately because the spec states it as an absolute: there is
    no trust score, ever, only a recompute command."""
    hits = []
    for p in sorted(HARNESS.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        text = p.read_text(encoding="utf-8", errors="replace").lower()
        if "trust_score" in text:
            hits.append(p.name)
    assert hits == [], f"trust_score appears in: {hits}"
