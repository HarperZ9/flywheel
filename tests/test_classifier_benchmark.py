import pytest

from train.classifier_benchmark import probabilities_from_envelope


def test_baseline_softmax_does_not_invent_abstention_training():
    score = {"scores": [{"choice_id": "a", "score": 1000, "eligible": True},
                        {"choice_id": "b", "score": 1000, "eligible": True},
                        {"choice_id": "c", "score": None, "eligible": False}]}
    out = probabilities_from_envelope(score)
    assert out == {"a": .5, "b": .5, "c": 0, "__abstain__": 0}


def test_neural_probabilities_renormalize_only_float_rounding_error():
    score = {"scores": [{"choice_id": "a", "probability_like": .50000001},
                        {"choice_id": "__abstain__", "probability_like": .5}]}
    assert sum(probabilities_from_envelope(score).values()) == pytest.approx(1)
    score["scores"][0]["probability_like"] = 2
    with pytest.raises(ValueError):
        probabilities_from_envelope(score)


def test_empty_eligibility_forces_abstention():
    score = {"scores": [{"choice_id": "a", "score": None, "eligible": False}]}
    assert probabilities_from_envelope(score) == {"a": 0, "__abstain__": 1}
