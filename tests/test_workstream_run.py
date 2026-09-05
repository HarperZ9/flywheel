"""Running a workstream: what gets checked, what gets skipped, and who is blamed.

The composition rule and the run schedule are two different pieces of code, and
the expensive failure is drift between them: a scheduler that runs a check the
rule would have called blocked wastes a proof-assistant invocation, and one that
skips a check the rule would have settled leaves a hole reading as a skip.

  1. THE SCHEDULE MATCHES THE RULE. Exactly the obligations that end up blocked
     are the ones never handed to a checker. This is asserted over a generated
     graph, not one hand-picked example.
  2. AN ABSENT CHECKER IS UNVERIFIABLE, NEVER A PASS. A kind nothing is
     registered for cannot quietly become established.
  3. A CRASHED CHECKER IS ATTRIBUTED TO THE HARNESS. It lands unverifiable with
     the exception named, not refuted, because our crash is not the statement's
     error.
  4. NO EXPRESSION EVALUATION. The arithmetic checker reads an interval and
     compares. There is no path where text out of a statement is executed.
  5. UNITS DO NOT BRIDGE FAMILIES. A litres-to-grams conversion is a refusal.
"""
import random

import pytest

from harness.workstream import (
    BLOCKED, REFUTED, UNVERIFIABLE, VERIFIED, Obligation, Workstream,
    WorkstreamError,
)
from harness.workstream_run import (
    _lean_environment, arithmetic_checker, default_checkers, dimensional_checker,
    lean_checker, run_workstream,
)

ENV = "lean4:v4.9.0+mathlib:2026-08-01"


def _ob(name, *, check="arithmetic", deps=(), statement=None, env=ENV):
    return Obligation(
        obligation_id=name,
        statement=statement or '{"value": 1, "interval": [0, 2]}',
        check=check,
        environment=env,
        depends_on=tuple(deps),
    )


def _fixed(verdicts):
    """A checker that answers from a table, and records what it was asked."""
    asked = []

    def checker(obligation):
        asked.append(obligation.obligation_id)
        return verdicts.get(obligation.obligation_id, "PASS")

    return checker, asked


def test_a_refuted_lemma_stops_the_stack_above_it_from_being_checked():
    stream = Workstream(
        [_ob("base"), _ob("mid", deps=("base",)), _ob("top", deps=("mid",))],
        goal="top",
    )
    checker, asked = _fixed({"base": "FAIL"})
    receipt = run_workstream(stream, {"arithmetic": checker})
    assert asked == ["base"]
    assert receipt["run"]["checked"] == 1
    assert receipt["run"]["skipped"] == 2
    assert receipt["obligations"]["mid"]["standing"] == BLOCKED
    assert receipt["obligations"]["top"]["standing"] == BLOCKED
    assert receipt["run"]["skipped_for"][0]["unsatisfied_dependency"] == "base"


def test_the_schedule_and_the_composition_rule_agree_on_a_generated_graph():
    rng = random.Random(20260904)
    for trial in range(60):
        size = rng.randint(2, 14)
        nodes = []
        for index in range(size):
            deps = tuple(sorted(rng.sample(range(index), rng.randint(0, min(index, 3)))))
            kind = rng.choice(["arithmetic", "arithmetic", "assumed"])
            nodes.append(_ob(
                f"n{index}",
                check=kind,
                deps=tuple(f"n{ref}" for ref in deps),
                statement="carried on trust" if kind == "assumed" else None,
            ))
        stream = Workstream(nodes, goal=f"n{size - 1}")
        table = {
            f"n{index}": rng.choice(["PASS", "PASS", "FAIL", "UNDECIDED", "UNVERIFIABLE"])
            for index in range(size)
        }
        checker, asked = _fixed(table)
        receipt = run_workstream(stream, {"arithmetic": checker})
        blocked = {name for name, record in receipt["obligations"].items()
                   if record["standing"] == BLOCKED}
        assumed = {node.obligation_id for node in nodes if node.check == "assumed"}
        # Everything the rule blocks was skipped, and everything else with a
        # checker behind it was run. Exactly once.
        assert set(asked) == set(receipt["obligations"]) - blocked - assumed, trial
        assert len(asked) == len(set(asked)), trial


def test_an_assumption_does_not_launder_a_refuted_dependency():
    # An assumption that names dependencies is conditional on them. Treating it
    # as satisfied regardless would let a withdrawn lemma reach the goal through
    # the one node nothing checks. The generated-graph test found this.
    stream = Workstream(
        [
            _ob("lemma"),
            _ob("scoped", check="assumed", deps=("lemma",),
                statement="granted, given the lemma below"),
            _ob("goal", deps=("scoped",)),
        ],
        goal="goal",
    )
    checker, asked = _fixed({"lemma": "FAIL"})
    receipt = run_workstream(stream, {"arithmetic": checker})
    assert asked == ["lemma"]
    assert receipt["obligations"]["scoped"]["standing"] == BLOCKED
    assert receipt["goal_standing"] == BLOCKED


def test_a_kind_with_no_registered_checker_is_unverifiable_not_a_pass():
    stream = Workstream([_ob("cited", check="citation", statement="RFC 9421 section 2.3")],
                        goal="cited")
    receipt = run_workstream(stream, {})
    assert receipt["goal_standing"] == UNVERIFIABLE
    assert "no checker is registered" in receipt["obligations"]["cited"]["detail"]


def test_a_crashed_checker_is_unverifiable_with_the_exception_named():
    def explode(_obligation):
        raise RuntimeError("the plate reader socket closed")

    stream = Workstream([_ob("reading", check="instrument", statement="absorbance")],
                        goal="reading")
    receipt = run_workstream(stream, {"instrument": explode})
    assert receipt["goal_standing"] == UNVERIFIABLE
    assert receipt["goal_standing"] != REFUTED
    detail = receipt["obligations"]["reading"]["detail"]
    assert "RuntimeError" in detail and "plate reader socket closed" in detail


def test_a_checker_returning_nonsense_is_refused_rather_than_interpreted():
    stream = Workstream([_ob("a")], goal="a")
    with pytest.raises(WorkstreamError, match="a checker returns"):
        run_workstream(stream, {"arithmetic": lambda _o: 17})


def test_an_unknown_kind_in_the_registry_is_refused():
    stream = Workstream([_ob("a")], goal="a")
    with pytest.raises(WorkstreamError, match="unknown check kind"):
        run_workstream(stream, {"telepathy": lambda _o: "PASS"})


@pytest.mark.parametrize("statement, expected", [
    ('{"value": 0.42, "interval": [0.4, 0.45]}', "PASS"),
    ('{"value": 0.5, "interval": [0.4, 0.45]}', "FAIL"),
    ('{"value": 0.4, "interval": [0.4, 0.45]}', "PASS"),
    ('{"value": 2, "interval": [4, 1]}', "PASS"),
    ('{"value": "0.42", "interval": [0.4, 0.45]}', "FAIL"),
    ('{"value": true, "interval": [0, 2]}', "FAIL"),
    ('{"value": 1}', "FAIL"),
    ("not json at all", "FAIL"),
])
def test_the_arithmetic_checker_reads_an_interval_and_never_evaluates(statement, expected):
    verdict, detail = arithmetic_checker(_ob("a", statement=statement))
    assert verdict == expected
    assert detail


def test_a_statement_that_looks_like_code_is_data_not_a_program():
    # The one property worth stating twice: nothing in this path executes text
    # that arrived in a statement.
    verdict, detail = arithmetic_checker(
        _ob("a", statement='{"value": 1, "interval": [0, 2], "note": "__import__(\'os\').system(\'echo\')"}'))
    assert verdict == "PASS"
    assert "1 lies inside" in detail


@pytest.mark.parametrize("statement, expected, fragment", [
    ('{"value": 500, "from": "mg", "to": "g", "expected": 0.5}', "PASS", "500"),
    ('{"value": 500, "from": "mg", "to": "g", "expected": 5}', "FAIL", "expected 5.0"),
    ('{"value": 1, "from": "L", "to": "g", "expected": 1000}', "FAIL", "bridging them"),
    ('{"value": 1, "from": "furlong", "to": "m", "expected": 201}', "FAIL", "no known family"),
    ('{"value": 1, "from": "mg", "to": "g"}', "FAIL", "missing expected"),
])
def test_the_dimensional_checker_refuses_across_families(statement, expected, fragment):
    verdict, detail = dimensional_checker(_ob("a", check="dimensional", statement=statement))
    assert verdict == expected
    assert fragment in detail


def test_the_lean_checker_refuses_an_admitted_hole_without_a_toolchain():
    # Lean exits 0 on sorry with only a warning, so this is the case where an
    # exit-code reading would call a false statement proved. No toolchain is
    # needed to see it.
    verdict, detail = lean_checker(
        _ob("a", check="lean", statement="theorem fermat : False := by sorry"))
    assert verdict == "FAIL"
    assert "sorry" in detail


def test_the_default_registry_covers_only_what_this_repository_can_decide():
    assert sorted(default_checkers()) == [
        "arithmetic", "dimensional", "instrument", "lean", "readback"]


def test_a_mixed_domain_stack_composes_end_to_end():
    """A dose claim over a conversion, a reading, and a statute nothing checks."""
    stream = Workstream(
        [
            Obligation("statute", "21 CFR 201.57(c)(3) requires the strength per unit",
                       "assumed", "cfr:2026-title21", ()),
            Obligation("conversion", '{"value": 500, "from": "mg", "to": "g", "expected": 0.5}',
                       "dimensional", "flywheel.units/v1", ()),
            Obligation("reading", '{"value": 0.5, "interval": [0.49, 0.51]}',
                       "arithmetic", "assay:hplc-2/cal-2026-08-30", ("conversion",)),
            Obligation("label", '{"value": 0.5, "interval": [0.45, 0.55]}',
                       "arithmetic", "flywheel.units/v1", ("reading", "statute")),
        ],
        goal="label",
    )
    receipt = run_workstream(stream)
    assert receipt["goal_standing"] == VERIFIED
    assert receipt["assumption_footprint"] == ["statute"]
    assert len(receipt["environment_footprint"]) == 3
    assert receipt["run"]["checked"] == 3
    assert any("conditional" in line for line in receipt["does_not_prove"])


@pytest.mark.parametrize("environment, toolchain, matched, fragment", [
    ("lean4:v4.9.0", "Lean (version 4.9.0, x86_64)", True, "matching the pinned"),
    # The version half matches and the library half does not bind, so the whole
    # string does not. A receipt printing "matching the pinned environment"
    # while nothing read the library is the failure this row exists to catch.
    ("lean4:v4.9.0+mathlib:2026-08-01", "Lean (version 4.9.0)", False,
     "no lake manifest was discoverable"),
    ("lean4:v4.9.0", "Lean (version 4.33.1)", False, "ran on 4.33.1"),
    ("lean4:4.9.0", "Lean (version 4.33.1)", False, "pins lean 4.9.0"),
    ("lean4", "Lean (version 4.33.1)", True, "names no lean version"),
    ("prove2me:mission-7", "Lean (version 4.33.1)", True, "names no lean version"),
    ("lean4:v4.9.0", "injected", False, "did not report a version"),
])
def test_a_pinned_lean_environment_is_confirmed_against_the_toolchain(
        environment, toolchain, matched, fragment):
    # The environment is folded into the workstream identity, so a receipt that
    # names a version the check did not run in reads stronger than it is.
    got, note = _lean_environment(environment, toolchain)
    assert got is matched
    assert fragment in note


def test_a_toolchain_mismatch_settles_unverifiable_not_refuted():
    from harness.lean_oracle import _lean_exe

    if _lean_exe() is None:
        pytest.skip("no lean toolchain on this machine")
    verdict, detail = lean_checker(
        _ob("a", check="lean", env="lean4:v0.0.1",
            statement="theorem a : 1 + 1 = 2 := rfl"))
    # The statement is true and the kernel accepted it. What is unverifiable is
    # the claim that it was decided in the environment the obligation names.
    assert verdict == "UNVERIFIABLE"
    assert "pins lean 0.0.1" in detail
