"""Decision results read each version with its own scope key."""
from harness.decision_evaluation import evaluate_cases
from harness.scope import LEGACY_SCOPE_KEY
from tests.test_decision_evaluation import case


def test_v1_and_v2_results_are_each_read_with_their_own_key():
    old = case("old")
    new = case("new")
    new["result"]["schema"] = "flywheel.decision-result/v2"
    new["result"]["scope"] = new["result"].pop(LEGACY_SCOPE_KEY)
    assert evaluate_cases([old, new])["counts"]["invalid_results"] == 0
    mixed = case("mixed")
    mixed["result"]["schema"] = "flywheel.decision-result/v2"
    assert evaluate_cases([mixed])["counts"]["invalid_results"] == 1
