import math
import hashlib

import pytest

from harness.classifier_calibration import fit_temperature, scale_distribution, select_threshold


def case(p, targets):
    return {"probabilities": {"a": p, "b": 1-p, "__abstain__": 0.0},
            "target_choice_ids": targets}


def test_temperature_reduces_overconfident_wrong_predictions_on_calibration_only():
    rows = [case(.99, ["a"]), case(.99, ["b"])]
    report = fit_temperature(rows)
    assert report["temperature"] > 1
    assert report["fitted_log_loss"] < report["raw_log_loss"]
    assert report["calibration_examples"] == 2
    assert report["status"] == "diagnostic_fit"


def test_temperature_preserves_masked_zero_and_order():
    out = scale_distribution({"a": .8, "b": .2, "__abstain__": 0.0}, 2)
    assert out["a"] == pytest.approx(2/3)
    assert out["__abstain__"] == 0
    assert sum(out.values()) == pytest.approx(1)


def test_no_threshold_is_promoted_from_tiny_perfect_sample():
    report = select_threshold([case(.99, ["a"])] * 5, thresholds=[.9])
    assert report["threshold"] is None
    assert report["status"] == "insufficient_risk_evidence"
    assert report["candidates"][0]["upper_error_bound"] > .05


def test_fixed_threshold_with_sufficient_zero_errors_has_known_exact_bound():
    rows = [{**case(.99, ["a"]), "case_id": str(i), "source_group": str(i),
             "input_sha256": hashlib.sha256(str(i).encode()).hexdigest(),
             "label_kind": "verified_outcome"} for i in range(100)]
    report = select_threshold(rows, thresholds=[.9])
    assert report["threshold"] == .9
    assert report["candidates"][0]["upper_error_bound"] == pytest.approx(1-.05**.01)
    assert report["status"] == "statistical_candidate_only"
    assert report["requires_independent_outcome_validation"] is True


def test_repeated_unidentified_outcomes_never_produce_a_threshold():
    report = select_threshold([case(.99, ["a"])] * 100, thresholds=[.9])
    assert report["threshold"] is None
    assert report["outcome_unit_status"] == "missing_outcome_identity"


def test_duplicate_declared_units_reject():
    row = {**case(.99, ["a"]), "case_id": "one", "source_group": "one",
           "input_sha256": "a"*64, "label_kind": "verified_outcome"}
    with pytest.raises(ValueError, match="outcome units"):
        select_threshold([row, row])


def test_wrong_high_confidence_and_abstention_do_not_inflate_coverage():
    rows = [case(.99, ["b"])] * 80 + [
        {"probabilities": {"a": .01, "b": .01, "__abstain__": .98},
         "target_choice_ids": []}] * 20
    report = select_threshold(rows, thresholds=[.9])
    assert report["threshold"] is None
    assert report["candidates"][0]["selected"] == 80
    assert report["candidates"][0]["errors"] == 80


@pytest.mark.parametrize("probs,temp", [({"a": math.nan}, 1), ({"a": 2}, 1),
    ({"a": 1}, 0), ({"a": 1}, True), ({"a": True}, 1)])
def test_malformed_distributions_fail(probs, temp):
    with pytest.raises(ValueError):
        scale_distribution(probs, temp)


def test_huge_numeric_input_raises_value_error():
    with pytest.raises(ValueError):
        scale_distribution({"a": 10**5000}, 1)
