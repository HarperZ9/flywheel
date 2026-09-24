import json
from copy import deepcopy

from harness.classifier_workflows import score_workflow_batch
from harness.evidence_json import canonical_sha256
from tests.test_classifier_model import request


class Scorer:
    def __init__(self, mismatch=False):
        self.calls = []
        self.mismatch = mismatch

    def score_batch(self, requests, *, task_family):
        self.calls.append((task_family, len(requests)))
        return [{"task_family": task_family, "model_ref": "test-model",
                 "request_sha256": "wrong" if self.mismatch else canonical_sha256(r),
                 "candidate_ids": [c["id"] for c in r["choices"]],
                 "scores": [{"choice_id": c["id"], "eligible": True, "score": 1}
                            for c in r["choices"]]} for r in requests]


def packets():
    return [{"task_family": family, "request": request(str(i), "Find parser tests")}
            for i, family in enumerate(["routing", "tool_selection", "routing"])]


def test_independent_same_family_requests_batch_and_restore_order():
    scorer = Scorer()
    source = packets()
    original = deepcopy(source)
    result = score_workflow_batch(source, scorer)
    assert scorer.calls == [("routing", 2), ("tool_selection", 1)]
    assert [r["task_family"] for r in result] == [p["task_family"] for p in source]
    assert all(r["status"] == "scored_shadow" for r in result)
    assert all(r["proposal"]["disposition"] == "abstained" for r in result)
    assert source == original


def test_misbound_scores_are_discarded_and_cannot_be_used():
    result = score_workflow_batch(packets(), Scorer(mismatch=True))
    assert all(r["status"] == "scorer_unavailable" for r in result)
    assert all(r["scores"] is None for r in result)
    assert all(r["proposal"]["choice_id"] is None for r in result)


def test_failure_preserves_fallback_instead_of_fabricating_confidence():
    class Failed:
        def score_batch(self, requests, *, task_family):
            raise RuntimeError("internal private endpoint detail")

    result = score_workflow_batch(packets(), Failed())
    assert all(r["scores"] is None for r in result)
    assert all(r["fallback_required"] for r in result)
    assert "private endpoint" not in str(result)


def test_scorer_extras_do_not_enter_shadow_report():
    class Extra(Scorer):
        def score_batch(self, requests, *, task_family):
            rows = super().score_batch(requests, task_family=task_family)
            for row in rows:
                row["private_detail"] = "should-not-leak"
                row["selection"] = {"automatic_selection_enabled": True}
                row["scores"][0]["private_detail"] = "should-not-leak"
            return rows

    results = score_workflow_batch(packets(), Extra())
    assert all(r["status"] == "scored_shadow" for r in results)
    assert "should-not-leak" not in str(results)
    assert all(r["scores"]["automatic_selection_enabled"] is False for r in results)


def test_scorer_exception_leaves_its_type_and_no_text():
    class Failed:
        def score_batch(self, requests, *, task_family):
            raise RuntimeError("internal private endpoint detail")

    result = score_workflow_batch(packets(), Failed())
    assert [r["scorer_error_type"] for r in result] == ["RuntimeError"] * 3
    assert {r["scorer_error_stage"] for r in result} == {"score_batch"}
    assert all(r["status"] == "scorer_unavailable" for r in result)
    assert "private endpoint" not in json.dumps(result)


def test_one_failing_family_does_not_mark_another():
    class FailsRouting(Scorer):
        def score_batch(self, requests, *, task_family):
            if task_family == "routing":
                raise TimeoutError("slow backend")
            return super().score_batch(requests, task_family=task_family)

    result = score_workflow_batch(packets(), FailsRouting())
    assert [(r["task_family"], r["status"], r["scorer_error_type"]) for r in result] == [
        ("routing", "scorer_unavailable", "TimeoutError"),
        ("tool_selection", "scored_shadow", None),
        ("routing", "scorer_unavailable", "TimeoutError")]


def test_misbound_scores_are_a_binding_failure_not_a_scorer_exception():
    result = score_workflow_batch(packets(), Scorer(mismatch=True))
    assert {(r["scorer_error_type"], r["scorer_error_stage"]) for r in result} == {
        ("ValueError", "binding")}


def test_scored_decisions_carry_empty_error_fields():
    result = score_workflow_batch(packets(), Scorer())
    assert [(r["scorer_error_type"], r["scorer_error_stage"]) for r in result] == [(None, None)] * 3


def test_exception_class_named_from_data_is_not_echoed():
    leaky = type("secret token value", (Exception,), {})

    class Failed:
        def score_batch(self, requests, *, task_family):
            raise leaky("private")

    result = score_workflow_batch(packets(), Failed())
    assert {r["scorer_error_type"] for r in result} == {"Exception"}
    assert "secret" not in json.dumps(result)
