import math

import pytest

from harness.classifier_metrics import (
    ClassifierMetricError,
    evaluate_probability_cases,
)


def case(case_id, target, probabilities):
    return {
        "case_id": case_id,
        "choice_ids": ["local", "hosted"],
        "target_choice_ids": target,
        "probabilities": probabilities,
    }


def test_probability_metrics_use_independent_targets_not_predicted_labels():
    report = evaluate_probability_cases([
        case("right", ["local"], {"local": 0.7, "hosted": 0.2, "__abstain__": 0.1}),
        case("wrong", ["hosted"], {"local": 0.6, "hosted": 0.3, "__abstain__": 0.1}),
        case("defer", [], {"local": 0.2, "hosted": 0.2, "__abstain__": 0.6}),
    ], bins=3)

    assert report["counts"] == {
        "total": 3,
        "probability_observed": 3,
        "probability_missing": 0,
        "correct_top1": 2,
        "wrong_top1": 1,
    }
    assert report["metrics"]["top1_accuracy"] == 2 / 3
    assert report["metrics"]["brier"] == pytest.approx((0.14 + 0.86 + 0.24) / 3)
    assert report["metrics"]["log_loss"] == pytest.approx(
        -(math.log(0.7) + math.log(0.3) + math.log(0.6)) / 3
    )
    assert report["confidence_semantics"] == (
        "confidence is max predicted class probability from the supplied "
        "distribution; it is not evidence of calibration"
    )
    assert "does not assert model calibration" in " ".join(report["does_not_prove"])


def test_coverage_error_curve_sorts_by_confidence_and_counts_bins():
    report = evaluate_probability_cases([
        case("high-wrong", ["hosted"], {"local": 0.9, "hosted": 0.05, "__abstain__": 0.05}),
        case("mid-right", ["hosted"], {"local": 0.2, "hosted": 0.6, "__abstain__": 0.2}),
        case("low-right", [], {"local": 0.3, "hosted": 0.3, "__abstain__": 0.4}),
    ], bins=3)

    assert report["coverage_error_curve"] == [
        {"threshold": 0.9, "covered": 1, "coverage": 1 / 3, "errors": 1, "error_rate": 1.0},
        {"threshold": 0.6, "covered": 2, "coverage": 2 / 3, "errors": 1, "error_rate": 0.5},
        {"threshold": 0.4, "covered": 3, "coverage": 1.0, "errors": 1, "error_rate": 1 / 3},
    ]
    assert [row["count"] for row in report["confidence_bins"]] == [0, 2, 1]
    assert report["confidence_bins"][1]["correct"] == 2
    assert report["confidence_bins"][2]["correct"] == 0


def test_missing_probabilities_leave_probabilistic_metrics_null():
    report = evaluate_probability_cases([
        case("missing", ["local"], None),
    ])

    assert report["counts"]["probability_observed"] == 0
    assert report["metrics"] == {
        "top1_accuracy": None,
        "brier": None,
        "log_loss": None,
        "probability_coverage": 0.0,
    }
    assert report["coverage_error_curve"] == []


@pytest.mark.parametrize("probabilities", [
    {"local": 1.1, "hosted": -0.1, "__abstain__": 0.0},
    {"local": 0.5, "hosted": 0.4, "__abstain__": 0.2},
    {"local": float("nan"), "hosted": 1.0, "__abstain__": 0.0},
    {"local": 0.5, "hosted": 0.5},
])
def test_invalid_distributions_reject_instead_of_scoring(probabilities):
    with pytest.raises(ClassifierMetricError):
        evaluate_probability_cases([case("bad", ["local"], probabilities)])


def test_unknown_or_contradictory_targets_reject_the_metric_input():
    with pytest.raises(ClassifierMetricError):
        evaluate_probability_cases([case("unknown", ["remote"], None)])
    with pytest.raises(ClassifierMetricError):
        evaluate_probability_cases([case("duplicate", ["local", "local"], None)])
