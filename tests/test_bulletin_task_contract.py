"""False-success controls for an independently supplied Bulletin task."""
from copy import deepcopy
import json

import pytest

from harness.bulletin_task_contract import evaluate_handoff, validate_contract


def fixture():
    contract = {
        "schema": "flywheel.bulletin-task-contract/v1", "task_id": "incident-1",
        "actor_a": "a" * 43, "actor_b": "b" * 43, "room": "scratch",
        "source_id": "123-source", "baseline_ids": ["123-source"],
        "source_payload": {"task_id": "incident-1", "state": "reported"},
        "result_payload": {"task_id": "incident-1", "state": "needs_review"},
        "max_writes": 1, "max_pages": 3, "page_size": 100,
        "max_response_bytes": 262144, "request_timeout_seconds": 5,
    }
    source = {"id": "123-source", "author": "a" * 43, "room": "scratch",
              "parent_id": None, "body": json.dumps(contract["source_payload"])}
    reply = {"id": "124-reply", "author": "b" * 43, "room": "scratch",
             "parent_id": "123-source", "body": json.dumps(contract["result_payload"])}
    observation = {"source": source, "posts": [reply, source], "gaps": []}
    return contract, observation


def test_positive_and_no_invented_transport_counts():
    c, o = fixture()
    r = evaluate_handoff(c, o)
    assert r["verdict"] == "PASS"
    assert r["task_success"] == {"numerator": 1, "denominator": 1}
    assert r["attempted_writes"] is None
    assert r["delivered_writes"] is None
    assert r["accepted_room_writes"] == 1
    assert "native_host_actions_unobserved" in r["coverage_gaps"]


@pytest.mark.parametrize(("field", "value", "code"), [
    ("author", "a" * 43, "reply_actor_mismatch"),
    ("parent_id", "other-parent", "reply_parent_mismatch"),
    ("room", "lobby", "reply_room_mismatch"),
    ("body", '{"task_id":"incident-1","state":"closed"}', "reply_payload_mismatch"),
    ("body", '{"task_id":"other-task","state":"needs_review"}', "reply_missing"),
])
def test_valid_json_cannot_override_independent_semantics(field, value, code):
    c, o = fixture()
    o["posts"][0][field] = value
    r = evaluate_handoff(c, o)
    assert r["verdict"] != "PASS"
    assert code in r["failure_codes"]


def test_duplicate_accepted_effects_and_unmarked_writes():
    c, o = fixture()
    duplicate = deepcopy(o["posts"][0])
    duplicate["id"] = "125-duplicate"
    o["posts"].append(duplicate)
    r = evaluate_handoff(c, o)
    assert r["verdict"] == "FAIL"
    assert r["accepted_room_writes"] == 2
    assert "multiple_task_replies" in r["failure_codes"]
    duplicate["body"] = "I completed the task"
    assert "write_budget_exceeded" in evaluate_handoff(c, o)["failure_codes"]


@pytest.mark.parametrize("gap", ["page_limit", "read_failed", "snapshot_changed"])
def test_incomplete_observation_cannot_pass(gap):
    c, o = fixture()
    o["gaps"] = [gap]
    assert evaluate_handoff(c, o)["verdict"] == "UNVERIFIABLE"


def test_changed_source_does_not_pass():
    c, o = fixture()
    o["source"]["body"] = '{"task_id":"incident-1","state":"closed"}'
    assert "source_payload_mismatch" in evaluate_handoff(c, o)["failure_codes"]


def test_contract_is_exact_bounded_and_not_actor_mutable():
    c, _ = fixture()
    validated = validate_contract(c)
    c["result_payload"]["state"] = "closed"
    assert validated["result_payload"]["state"] == "needs_review"
    for key, bad in [("max_pages", True), ("max_pages", 101),
                     ("actor_b", "bad"), ("baseline_ids", []),
                     ("result_payload", {"task_id": "other"})]:
        mutated = deepcopy(c)
        mutated[key] = bad
        with pytest.raises(ValueError):
            validate_contract(mutated)


def test_duplicate_json_keys_are_not_a_valid_completion():
    c, o = fixture()
    o["posts"][0]["body"] = '{"task_id":"incident-1","state":"closed","state":"needs_review"}'
    assert evaluate_handoff(c, o)["verdict"] != "PASS"


def test_json_boolean_is_not_a_numeric_contract_value():
    c, o = fixture()
    c["result_payload"]["severity"] = 1
    o["posts"][0]["body"] = json.dumps({**c["result_payload"], "severity": True})
    assert "reply_payload_mismatch" in evaluate_handoff(c, o)["failure_codes"]


def test_missing_parent_field_is_incomplete_evidence():
    c, o = fixture()
    del o["posts"][0]["parent_id"]
    assert evaluate_handoff(c, o)["verdict"] == "UNVERIFIABLE"
