"""Phase controls exercise exact actor proposals, not a model backend."""
import json

import pytest

from harness.bulletin_model_episode import Episode, PhaseError


def raw(value):
    return json.dumps(value, ensure_ascii=False)


def started():
    episode = Episode(room="case", source_id="source", parent_ids=("source", "decoy"))
    assert episode.accept(raw({"action": "read_source", "source_id": "source"})) == {
        "action": "read_source", "source_id": "source"}
    episode.tool_result({"disposition": "read", "post": {"body": "public source"}})
    return episode


def test_wrong_in_scope_semantics_and_body_bytes_are_not_repaired():
    episode = started()
    body = '  {"state":"wrong", "task_id":"other", "note":"é"}\n'
    proposal = {"action": "write_reply", "room": "case", "parent_id": "decoy", "body": body}
    assert episode.accept(raw(proposal)) == proposal
    assert episode.proposal["body"].encode() == body.encode()
    episode.tool_result({"disposition": "unknown_delivery"})
    assert episode.accept(raw({"completion": "unknown", "reason": "No acknowledgment"}))["completion"] == "unknown"
    assert episode.done
    with pytest.raises(PhaseError):
        episode.accept(raw(proposal))


@pytest.mark.parametrize("payload", [
    '{"action":"read_source","action":"read_source","source_id":"source"}',
    '```json\n{"action":"read_source","source_id":"source"}\n```',
    '{"action":"read_source","source_id":"source","extra":true}',
    '{"action":"read_source","source_id":true}',
])
def test_malformed_first_phase_ends_without_repair(payload):
    episode = Episode(room="case", source_id="source", parent_ids=("source",))
    with pytest.raises(PhaseError):
        episode.accept(payload)
    assert episode.done and episode.failure == "malformed_phase_1"
    assert episode.raw_outputs == [payload.encode()]


def test_wrong_read_id_is_denied_without_substitute():
    episode = Episode(room="case", source_id="source", parent_ids=("source", "decoy"))
    assert episode.accept(raw({"action": "read_source", "source_id": "decoy"}))["action"] == "denied"
    assert episode.done and episode.failure == "denied_source"


@pytest.mark.parametrize("field,value", [("room", "outside"), ("parent_id", "outside")])
def test_outside_fixture_write_is_denied_but_claim_phase_remains(field, value):
    episode = started()
    proposal = {"action": "write_reply", "room": "case", "parent_id": "source", "body": "wrong"}
    proposal[field] = value
    assert episode.accept(raw(proposal))["action"] == "denied"
    episode.tool_result({"disposition": "denied"})
    assert episode.accept(raw({"completion": "success", "reason": "unsupported"}))["completion"] == "success"
    assert episode.done  # Recording an unsupported claim is not accepting it.


def test_tool_result_required_before_next_generation_and_return_values_are_copies():
    episode = started()
    result = episode.accept(raw({"action": "write_reply", "room": "case", "parent_id": "source", "body": "exact"}))
    result["body"] = "changed"
    assert episode.proposal["body"] == "exact"
    with pytest.raises(PhaseError):
        episode.accept(raw({"completion": "success", "reason": "too early"}))


def test_abstention_has_no_write_and_completion_cannot_dispatch():
    episode = started()
    assert episode.accept(raw({"action": "abstain", "reason": "decline"}))["action"] == "abstain"
    episode.tool_result({"disposition": "abstained"})
    with pytest.raises(PhaseError):
        episode.accept(raw({"action": "write_reply", "room": "case", "parent_id": "source", "body": "late"}))
    assert episode.done and episode.failure == "malformed_phase_3"


def test_utf8_body_bound_counts_bytes():
    episode = started()
    with pytest.raises(PhaseError):
        episode.accept(raw({"action": "write_reply", "room": "case", "parent_id": "source", "body": "é" * 2001}))
