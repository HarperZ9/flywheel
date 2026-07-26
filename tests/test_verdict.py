from harness.verdict import (
    Verdict, Execution, Attribution, UndecidedReason, UnverifiableReason,
    is_dispositive, attribution_for,
)


def test_four_verdicts_exist_and_are_strings():
    assert Verdict.PASS == "PASS"
    assert Verdict.FAIL == "FAIL"
    assert Verdict.UNDECIDED == "UNDECIDED"
    assert Verdict.UNVERIFIABLE == "UNVERIFIABLE"
    assert len(list(Verdict)) == 4


def test_only_pass_and_fail_are_dispositive():
    assert is_dispositive(Verdict.PASS) is True
    assert is_dispositive(Verdict.FAIL) is True
    assert is_dispositive(Verdict.UNDECIDED) is False
    assert is_dispositive(Verdict.UNVERIFIABLE) is False


def test_candidate_attributable_executions_blame_the_candidate():
    # A candidate that loops forever or crashes the checker earned its FAIL.
    assert attribution_for(Execution.TIMEOUT) is Attribution.CANDIDATE
    assert attribution_for(Execution.CRASHED) is Attribution.CANDIDATE
    assert attribution_for(Execution.RESOURCE_EXCEEDED) is Attribution.CANDIDATE


def test_harness_and_environment_failures_never_blame_the_candidate():
    # Training on these would teach the model that our bugs are its fault.
    assert attribution_for(Execution.HARNESS_ERROR) is Attribution.HARNESS
    assert attribution_for(Execution.TOOLCHAIN_MISSING) is Attribution.ENVIRONMENT


def test_completed_execution_attributes_to_the_candidate():
    assert attribution_for(Execution.COMPLETED) is Attribution.CANDIDATE


def test_reason_enums_are_closed_vocabularies_not_free_text():
    assert UndecidedReason.HELD_OUT_DISAGREEMENT == "HELD_OUT_DISAGREEMENT"
    assert UnverifiableReason.ORACLE_UNAVAILABLE == "ORACLE_UNAVAILABLE"
    assert "OUT_OF_SCOPE" in {r.value for r in UndecidedReason}
    assert "RECEIPT_COMMIT_FAILED" in {r.value for r in UndecidedReason}
