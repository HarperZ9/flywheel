"""Criteria start failing and only a NAMED oracle can flip one.

The rule this file defends: there is no code path where model text flips a
criterion. A criterion is created failing, and the only mutator requires the
oracle name registered for it. That is what keeps a learned model off the
accept path when the loop reports "done".
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness import acceptance_criteria as AC  # noqa: E402

SPECS = [
    {"id": "tests_green", "description": "the suite passes", "oracle": "pytest"},
    {"id": "no_slop", "description": "prose gate clean", "oracle": "check_writing"},
]


def test_every_criterion_starts_failing():
    c = AC.new_criteria(SPECS)
    assert [x["status"] for x in c] == [AC.FAILING, AC.FAILING]
    assert all(x["evidence"] is None for x in c)
    assert not AC.all_pass(c)


def test_a_spec_cannot_declare_itself_passing():
    c = AC.new_criteria([dict(SPECS[0], status=AC.PASSING)])
    assert c[0]["status"] == AC.FAILING


def test_the_registered_oracle_flips_it():
    c = AC.new_criteria(SPECS)
    rec = AC.apply_oracle_result(c, "tests_green", "pytest", True, evidence="42 passed")
    assert rec["from"] == AC.FAILING and rec["to"] == AC.PASSING
    assert c[0]["status"] == AC.PASSING
    assert c[0]["evidence"] == "42 passed"
    assert not AC.all_pass(c)          # the other one is still failing


def test_a_different_oracle_cannot_vouch():
    c = AC.new_criteria(SPECS)
    with pytest.raises(AC.CriteriaError):
        AC.apply_oracle_result(c, "tests_green", "the_model_said_so", True)
    assert c[0]["status"] == AC.FAILING


def test_an_unknown_criterion_is_refused():
    c = AC.new_criteria(SPECS)
    with pytest.raises(AC.CriteriaError):
        AC.apply_oracle_result(c, "no_such", "pytest", True)


def test_a_false_result_flips_back():
    c = AC.new_criteria(SPECS)
    AC.apply_oracle_result(c, "tests_green", "pytest", True)
    rec = AC.apply_oracle_result(c, "tests_green", "pytest", False, evidence="1 failed")
    assert rec["from"] == AC.PASSING and rec["to"] == AC.FAILING
    assert c[0]["status"] == AC.FAILING


def test_all_pass_needs_every_criterion():
    c = AC.new_criteria(SPECS)
    AC.apply_oracle_result(c, "tests_green", "pytest", True)
    assert not AC.all_pass(c)
    AC.apply_oracle_result(c, "no_slop", "check_writing", True)
    assert AC.all_pass(c)
    assert AC.failing(c) == []


def test_an_empty_criteria_set_is_refused():
    # A set that requires nothing would accept everything.
    with pytest.raises(AC.CriteriaError):
        AC.new_criteria([])


def test_duplicate_ids_and_missing_fields_are_refused():
    with pytest.raises(AC.CriteriaError):
        AC.new_criteria([SPECS[0], SPECS[0]])
    with pytest.raises(AC.CriteriaError):
        AC.new_criteria([{"id": "x", "description": "no oracle named"}])


def test_summary_reports_the_state():
    c = AC.new_criteria(SPECS)
    AC.apply_oracle_result(c, "tests_green", "pytest", True)
    s = AC.summary(c)
    assert s["total"] == 2 and s["passing"] == 1
    assert s["failing_ids"] == ["no_slop"] and s["all_pass"] is False


def test_does_not_prove_is_carried():
    codes = " ".join(AC.does_not_prove())
    assert "NOT_PROVES_TASK_DONE" in codes
    assert "NOT_PROVES_ORACLE_QUALITY" in codes


def test_no_public_function_flips_a_criterion_without_an_oracle():
    """The structural guarantee, checked against the module's own source: the
    only assignment to a criterion's status lives in apply_oracle_result."""
    src = (Path(__file__).resolve().parent.parent / "harness"
           / "acceptance_criteria.py").read_text(encoding="utf-8")
    # Count ASSIGNMENTS only. An earlier version of this test matched the bare
    # substring, so it also matched `== ` and pushed the module into writing
    # comparisons backwards to dodge it: the test was bending the code instead
    # of describing it. A negative lookahead for `=` keeps the guarantee while
    # letting the module read naturally.
    import re
    assigns = re.findall(r'\["status"\]\s*=(?!=)', src)
    assert len(assigns) == 1, f"status is assigned in {len(assigns)} places, want 1"


def test_the_loop_never_assigns_a_criterion_status_directly():
    """The module-side pin guards acceptance_criteria.py; criteria are plain
    dicts, so the file that WIRES them must not bypass apply_oracle_result."""
    import re
    src = (Path(__file__).resolve().parent.parent / "harness"
           / "local_loop.py").read_text(encoding="utf-8")
    assert re.findall(r'\["status"\]\s*=(?!=)', src) == []
    calls = re.findall(r"apply_oracle_result\(", src)
    assert len(calls) == 1, f"{len(calls)} flip sites in the loop, want exactly 1"
    assert '"test_cmd"' in src
