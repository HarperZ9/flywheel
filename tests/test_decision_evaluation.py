"""Offline controls, not measurements of model performance."""
import pytest

from harness.decision_contract import evaluate_proposal
from harness.decision_evaluation import evaluate_cases, synthetic_control_report


def test_deep_malformed_result_is_invalid_with_unavailable_input_hash():
    item = case("deep")
    nested = None
    for _ in range(1100): nested = [nested]
    item["result"]["reason_code"] = nested
    report = evaluate_cases([item])
    assert report["counts"]["invalid_results"] == 1
    assert report["metrics"]["overall_correct_fraction"] == 0
    assert report["input_sha256"] is None
    assert report["input_sha256_error"] == "input_not_canonical_json"


_DIGEST0, _DIGEST1 = "0" * 64, "1" * 64


def result(choice="search"):
    return {
        "schema": "flywheel.decision-result/v1",
        "disposition": "abstained" if choice is None else "selected",
        "choice_id": choice,
        "reason_code": "abstain" if choice is None else "selected",
        "evidence_refs": [],
        "request_sha256": _DIGEST0,
        "response_sha256": _DIGEST1,
        "scorer_ref": "control",
        "does_not_prove": "synthetic control fixture only",
    }


def request(*, eligible=None):
    return {
        "schema": "flywheel.decision-request/v1",
        "decision_ref": "decision_eval",
        "state": "Choose a route.",
        "choices": [
            {"id": "search", "description": "Search local evidence."},
            {"id": "reason", "description": "Use internal reasoning."},
            {"id": "remote", "description": "Use the remote route."},
        ],
        "eligible_choice_ids": ["search", "reason"] if eligible is None else eligible,
        "evidence_refs": ["ev_one"],
    }


def case(ref, choice="search", *, expect_abstain=False, **extra):
    return {
        "case_id": ref,
        "declared_choice_ids": ["search", "reason", "remote"],
        "eligible_choice_ids": ["search", "reason"],
        "acceptable_choice_ids": [] if expect_abstain else ["search"],
        "expect_abstain": expect_abstain,
        "result": result(choice),
        **extra,
    }


def evaluation_case(ref, proposal_result, *, eligible=None):
    return case(
        ref, None, expect_abstain=True, result=proposal_result,
        eligible_choice_ids=["search", "reason"] if eligible is None else eligible)


def test_always_abstain_cannot_look_like_perfect_task_success():
    report = evaluate_cases([case("one", None), case("two", None)])
    assert report["metrics"]["selection_coverage"] == 0
    assert report["metric_denominators"]["selective_accuracy"] == 0
    assert report["metrics"]["selective_accuracy"] is None
    assert report["metrics"]["overall_correct_fraction"] == 0
    assert report["counts"]["unnecessary_abstentions"] == 2


def test_schema_valid_wrong_choice_is_not_success():
    report = evaluate_cases([case("wrong", "reason")])
    assert report["counts"]["invalid_results"] == 0
    assert report["counts"]["wrong_selections"] == 1
    assert report["metrics"]["overall_correct_fraction"] == 0


@pytest.mark.parametrize(
    ("name", "proposal"),
    [
        ("unknown-choice", lambda: evaluate_proposal(
            request(), '{"choice_id": "invented", "evidence_refs": []}',
            scorer_ref="control")),
        ("malformed", lambda: evaluate_proposal(
            request(), "not json", scorer_ref="control")),
        ("duplicate-key", lambda: evaluate_proposal(
            request(), '{"choice_id": "search", "choice_id": "reason", "evidence_refs": []}',
            scorer_ref="control")),
        ("invalid-shape", lambda: evaluate_proposal(
            request(), '{"choice_id": "search", "evidence_refs": [], "confidence": 0.7}',
            scorer_ref="control")),
        ("invented-evidence", lambda: evaluate_proposal(
            request(), '{"choice_id": null, "evidence_refs": ["invented"]}',
            scorer_ref="control")),
        ("ineligible", lambda: evaluate_proposal(
            request(eligible=["search"]), '{"choice_id": "reason", "evidence_refs": []}',
            scorer_ref="control")),
        ("invalid-scorer", lambda: evaluate_proposal(
            request(), '{"choice_id": "search", "evidence_refs": []}',
            scorer_ref="bad scorer")),
        ("oversize", lambda: evaluate_proposal(
            request(), "x" * 4097, scorer_ref="control")),
    ],
)
def test_contract_rejections_are_counted_separately_from_abstention_quality(name, proposal):
    report = evaluate_cases([evaluation_case(name, proposal())])

    assert report["counts"]["rejected_proposals"] == 1
    assert report["counts"]["abstained"] == 0
    assert report["metrics"]["overall_correct_fraction"] == 0
    assert report["cases"] == [{"case_id": name, "outcome": "rejected_proposals"}]


def test_empty_eligibility_reject_is_not_success_and_mismatch_is_invalid():
    proposal = evaluate_proposal(
        request(eligible=[]), '{"choice_id": "search", "evidence_refs": []}',
        scorer_ref="control")
    matched = evaluate_cases([evaluation_case("empty-eligible", proposal, eligible=[])])
    mismatch = evaluate_cases([evaluation_case("empty-mismatch", proposal)])

    assert proposal["reason_code"] == "empty_eligibility"
    assert matched["counts"]["rejected_proposals"] == 1
    assert matched["counts"]["correct_abstentions"] == 0
    assert matched["metrics"]["overall_correct_fraction"] == 0
    assert mismatch["counts"]["invalid_results"] == 1
    assert mismatch["counts"]["rejected_proposals"] == 0


def test_eligibility_and_abstention_errors_have_distinct_denominators():
    report = evaluate_cases([
        case("right"), case("wrong", "reason"), case("forbidden", "remote"),
        case("defer", None, expect_abstain=True),
        case("should-defer", "search", expect_abstain=True),
    ])
    assert report["counts"]["total"] == 5
    assert report["counts"]["ineligible_selections"] == 1
    assert report["counts"]["correct_abstentions"] == 1
    assert report["counts"]["missed_abstentions"] == 1
    assert report["metric_denominators"] == {
        "selection_coverage": 5,
        "selective_accuracy": 4,
        "overall_correct_fraction": 5,
        "abstention_precision": 1,
        "abstention_recall": 2,
    }
    assert report["metrics"]["overall_correct_fraction"] == 2 / 5
    assert report["metrics"]["selective_accuracy"] == 1 / 4
    assert report["metrics"]["abstention_recall"] == 1 / 2


def test_unseen_choice_and_contradictory_disposition_cannot_be_correct():
    contradictory = case("contradictory")
    contradictory["result"]["disposition"] = "abstained"
    report = evaluate_cases([case("unknown", "invented"), contradictory])
    assert report["counts"]["invalid_results"] == 2
    assert report["metrics"]["overall_correct_fraction"] == 0


def test_missing_measurements_remain_unknown_and_partial_coverage_is_explicit():
    empty = evaluate_cases([case("unmeasured")])
    assert empty["measurements"]["latency_ms_p95"] is None
    assert empty["measurements"]["cost_usd_observed_sum"] is None
    report = evaluate_cases([
        case("measured", latency_ms=12.0, cost_usd=0.002),
        case("missing"),
    ])
    assert report["measurements"]["latency_observed_cases"] == 1
    assert report["measurements"]["cost_observed_cases"] == 1
    assert report["measurements"]["cost_usd_observed_sum"] == 0.002
    assert report["measurements"]["measurement_coverage_complete"] is False


@pytest.mark.parametrize("value", [True, -1, float("nan"), float("inf"), "12"])
def test_invalid_observed_latency_is_not_silently_counted(value):
    with pytest.raises(ValueError):
        evaluate_cases([case("bad", latency_ms=value)])


def test_duplicate_ids_and_impossible_labels_reject_the_experiment():
    with pytest.raises(ValueError):
        evaluate_cases([case("same"), case("same")])
    bad = case("bad")
    bad["acceptable_choice_ids"] = ["remote"]
    with pytest.raises(ValueError):
        evaluate_cases([bad])


def test_empty_evaluation_has_no_success_rate():
    report = evaluate_cases([])
    assert report["counts"]["total"] == 0
    assert report["metrics"]["overall_correct_fraction"] is None
    assert report["does_not_prove"]


def test_missing_choice_id_on_abstention_is_malformed_not_default_none():
    malformed = case("missing-choice", None)
    del malformed["result"]["choice_id"]
    report = evaluate_cases([malformed])
    assert report["counts"]["invalid_results"] == 1
    assert report["counts"]["abstained"] == 0
    assert report["metrics"]["overall_correct_fraction"] == 0


@pytest.mark.parametrize("extra", [
    {"confidence": 0.91},
    {"diagnostics": {"score": float("nan")}},
    {"diagnostics": [float("inf")]},
])
def test_malformed_result_payload_is_invalid_not_selected(extra):
    malformed = case("malformed")
    malformed["result"].update(extra)
    report = evaluate_cases([malformed])
    assert report["counts"]["invalid_results"] == 1
    assert report["counts"]["selected"] == 0
    assert report["metrics"]["selection_coverage"] == 0
    if "diagnostics" in extra:
        assert report["input_sha256"] is None
        assert report["input_sha256_error"] == "input_not_canonical_json"


def test_synthetic_control_report_is_deterministic_and_disclaims_model_quality():
    first = synthetic_control_report()
    second = synthetic_control_report()
    assert first == second
    assert first["schema"] == "flywheel.decision-control-report/v1"
    assert "no provider calls" in first["methodology"]
    assert "model quality" in " ".join(first["does_not_prove"])
    assert set(first["controls"]) == {
        "correct", "wrong_but_valid", "ineligible", "abstain_all",
        "rejected_when_abstention_expected",
    }
    assert first["controls"]["correct"]["counts"]["correct_selections"] == 1
    assert first["controls"]["wrong_but_valid"]["counts"]["wrong_selections"] == 1
    assert first["controls"]["ineligible"]["counts"]["ineligible_selections"] == 1
    assert first["controls"]["abstain_all"]["metrics"]["selective_accuracy"] is None
    rejected = first["controls"]["rejected_when_abstention_expected"]["counts"]
    assert rejected["rejected_proposals"] == 1
    assert rejected["correct_abstentions"] == 0

def test_unhashable_reason_code_is_invalid_result_not_exception():
    malformed = case("reason-list")
    malformed["result"]["reason_code"] = []
    report = evaluate_cases([malformed])
    assert report["counts"]["invalid_results"] == 1
    assert report["counts"]["selected"] == 0
    assert report["metrics"]["overall_correct_fraction"] == 0


@pytest.mark.parametrize(("choice", "reason_code"), [
    ("search", "abstain"),
    (None, "selected"),
])
def test_reason_code_must_match_disposition(choice, reason_code):
    mismatched = case("mismatched", choice)
    mismatched["result"]["reason_code"] = reason_code
    report = evaluate_cases([mismatched])
    assert report["counts"]["invalid_results"] == 1
    assert report["counts"]["selected"] == 0
    assert report["counts"]["abstained"] == 0
    assert report["metrics"]["overall_correct_fraction"] == 0

def test_null_response_digest_allowed_only_for_unhashable_abstain_reasons():
    oversize = case("oversize", None)
    oversize["result"].update({
        "reason_code": "response_oversize",
        "response_sha256": None,
    })
    invalid_shape = case("invalid-shape", None)
    invalid_shape["result"].update({
        "reason_code": "invalid_shape",
        "response_sha256": None,
    })
    report = evaluate_cases([oversize, invalid_shape])
    assert report["counts"]["invalid_results"] == 0
    assert report["counts"]["rejected_proposals"] == 2
    assert report["counts"]["unnecessary_abstentions"] == 0
    assert report["counts"]["selected"] == 0


def test_selected_result_with_null_response_digest_is_invalid():
    selected = case("selected-null-digest")
    selected["result"]["response_sha256"] = None
    report = evaluate_cases([selected])
    assert report["counts"]["invalid_results"] == 1
    assert report["counts"]["selected"] == 0
    assert report["metrics"]["overall_correct_fraction"] == 0

def test_report_names_unmounted_caller_supplied_result_boundary():
    report = evaluate_cases([case("boundary")])
    boundary = " ".join(report["does_not_prove"])
    assert "caller-supplied result authenticity" in boundary
    assert "mounted gateway admission" in boundary
