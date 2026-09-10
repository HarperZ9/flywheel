"""False-success controls for reconstruction custody, not reviewer competence."""
import hashlib
import json
import pytest

from test_bulletin_model_review import exchange, rows
from harness import bulletin_model_review as review


def mutate(value, fault):
    if fault == "old_minimal":
        return {key: value[key] for key in ("reviewer_id", "reviewer_type", "items")}
    if fault == "packet": value["items"][0]["packet_sha256"] = "0" * 64
    elif fault == "procedure": value["procedure_sha256"] = "0" * 64
    elif fault == "missing_provider": del value["reviewer_provider"]
    elif fault == "missing_disclosure": del value["disclosures"]["prior_access"]
    elif fault == "negative_usage": value["accounting"]["input_tokens"] = -1
    elif fault == "bool_count": value["accounting"]["invocation_count"] = True
    elif fault == "infinite_cost": value["accounting"]["cost_usd"] = float("inf")
    elif fault == "backward_time":
        value.update(started_at="2026-09-10T01:00:01Z", ended_at="2026-09-10T01:00:00Z")
    elif fault == "naive_time": value["started_at"] = "2026-09-10T01:00:00"
    elif fault == "item_outside_pass":
        value.update(started_at="2026-09-10T01:00:00Z", ended_at="2026-09-10T01:00:02Z")
        value["items"][0]["started_at"] = "2026-09-10T00:59:00Z"
    elif fault == "gap_complete": value["items"][0]["evidence_gaps"] = ["missing final page"]
    elif fault == "partial_without_gap": value["items"][0]["evidence_complete"] = False
    else:
        refs = value["items"][0]["record_pointers"]
        if fault == "missing_dimension": del refs["author"]
        elif fault == "unresolved_pointer": refs["author"]["pointers"][-1] = "/observation/posts/999/body"
        elif fault == "wrong_root": refs["author"]["pointers"][-1] = "/item_id"
        elif fault == "nonstring_pointer": refs["author"]["pointers"][-1] = []
        elif fault == "noncanonical_index": refs["author"]["pointers"][-1] = "/observation/posts/00/body"
        elif fault == "empty_interpretation": refs["author"]["interpretation"] = ""
        elif fault == "no_observation": refs["author"]["pointers"] = ["/contract/task_id"]
    return value


@pytest.mark.parametrize("fault", ["old_minimal", "packet", "procedure", "missing_provider", "missing_disclosure",
    "negative_usage", "bool_count", "infinite_cost", "backward_time", "naive_time", "item_outside_pass",
    "gap_complete", "partial_without_gap", "missing_dimension", "unresolved_pointer", "wrong_root",
    "nonstring_pointer", "noncanonical_index", "empty_interpretation", "no_observation"])
def test_missing_or_divergent_reconstruction_never_reveals_claims(exchange, fault):
    blind, control, _, context = exchange
    context["mutate"] = lambda value: mutate(value, fault)
    with pytest.raises(ValueError, match="blind_labels_invalid"):
        review.review_prefix(rows(), blind_store=blind, control_store=control)
    assert "blind-labels-frozen.json" not in control.records
    assert "claims-revealed.json" not in blind.records


@pytest.mark.parametrize("fault", ["claims_hash", "packet", "procedure", "missing_provider", "claim_pointer"])
def test_second_pass_requires_its_own_bound_reconstruction(exchange, fault):
    blind, control, _, context = exchange
    def change(value):
        if fault == "claims_hash": value["claims_sha256"] = "0" * 64
        elif fault == "claim_pointer": value["items"][0]["record_pointers"]["claim_support"]["pointers"][0] = "/claim/missing"
        else: value = mutate(value, fault)
        return value
    context["claim_mutate"] = change
    with pytest.raises(ValueError, match="claim_labels_invalid"):
        review.review_prefix(rows(), blind_store=blind, control_store=control)
    assert "claim-labels-frozen.json" not in control.records and "checker-revealed.json" not in blind.records


def test_unknowns_and_full_reconstruction_are_preserved_separately_from_actor_budget(exchange):
    blind, control, _, _ = exchange
    gate = review.review_prefix(rows(), blind_store=blind, control_store=control)
    receipt = json.loads(control.records["blind-review-receipt.json"])
    assert gate["blind_review_sha256"] == hashlib.sha256(control.records["blind-review-receipt.json"]).hexdigest()
    assert receipt["review_accounting"]["outside_actor_generation_budget"] is True
    assert receipt["review_accounting"]["statistical_independence_proven"] is False
    for phase in ("task_pass", "claim_pass"):
        value = receipt["review_accounting"][phase]
        assert value["reviewer_model"] == value["reviewer_provider"] == "unknown"
        assert value["accounting"]["invocation_count"] is value["accounting"]["cost_usd"] is None
        assert value["elapsed_reported_seconds"] is None and value["item_count"] == 4
        assert value["received_at"] <= value["frozen_at"] and value["human_validation"] is False
    labels = json.loads(control.records["blind-labels-frozen.json"])
    for label in labels["items"]:
        assert label["packet_sha256"] == hashlib.sha256(blind.records[label["item_id"] + ".json"]).hexdigest()
        assert len(label["record_pointers"]) == 6
    # These scripted pointers resolve but deliberately do not prove interpretation.
    assert gate["independent_review_agrees"] is True
