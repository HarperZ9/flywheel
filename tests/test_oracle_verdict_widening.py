import pytest

from harness.oracle import OracleResult, NonDispositiveVerdict
from harness.verdict import Verdict, Execution, Attribution


def _binary(passed: bool) -> OracleResult:
    return OracleResult(passed=passed, cmd="c", output_hash="h",
                        stdout_excerpt="", rc=0 if passed else 1)


def test_existing_binary_construction_still_works():
    # The 28 call sites in 13 modules must keep working unchanged.
    assert _binary(True).passed is True
    assert _binary(False).passed is False
    assert _binary(True).verdict() == "PASS"
    assert _binary(False).verdict() == "FAIL"


def test_binary_construction_infers_the_verdict():
    assert _binary(True).verdict_ is Verdict.PASS
    assert _binary(False).verdict_ is Verdict.FAIL


def test_undecided_can_be_constructed():
    r = OracleResult(verdict_=Verdict.UNDECIDED, cmd="c", output_hash="h",
                     stdout_excerpt="", rc=0)
    assert r.verdict() == "UNDECIDED"


def test_passed_raises_on_a_non_dispositive_verdict():
    # Silently returning False here would score an undecided rollout as a
    # failure: the escape hatch the design forbids.
    r = OracleResult(verdict_=Verdict.UNVERIFIABLE, cmd="c", output_hash="h",
                     stdout_excerpt="", rc=0)
    with pytest.raises(NonDispositiveVerdict):
        _ = r.passed


def test_defaults_are_completed_and_candidate_attributed():
    r = _binary(False)
    assert r.execution is Execution.COMPLETED
    assert r.attribution is Attribution.CANDIDATE


def test_harness_error_attributes_away_from_the_candidate():
    r = OracleResult(verdict_=Verdict.UNVERIFIABLE, cmd="c", output_hash="h",
                     stdout_excerpt="", rc=1,
                     execution=Execution.HARNESS_ERROR)
    assert r.attribution is Attribution.HARNESS


def test_constructing_with_neither_passed_nor_verdict_is_an_error():
    with pytest.raises(ValueError):
        OracleResult(cmd="c", output_hash="h", stdout_excerpt="", rc=0)
