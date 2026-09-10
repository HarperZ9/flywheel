"""Scripted orchestration controls are not measurements of model behavior."""
import json

from harness.bulletin_model_budget import CampaignBudget
from harness.bulletin_model_episode import Episode
from harness.bulletin_model_exchange import PrivateExchange
from harness.bulletin_model_episode import run_episode


def public_post(source="s", room="r"):
    return {"id": source, "author": "a" * 43, "room": room, "parent_id": None, "body": "public source"}


def ready_budget(store):
    budget = CampaignBudget(store, "campaign")
    for stage, tokens in (("readiness", 32), ("smoke", 256)):
        budget.finish(budget.reserve(stage, tokens), "response_received")
    return budget


def test_three_calls_one_write_unknown_delivery_then_independent_claim(tmp_path):
    body = ' {"task_id":"wrong","state":"incorrect"}\n'
    outputs = iter([
        {"action": "read_source", "source_id": "source"},
        {"action": "write_reply", "room": "room", "parent_id": "decoy", "body": body},
        {"completion": "unknown", "reason": "acknowledgment withheld"},
    ])
    invocations, writes = [], []
    def invoke(**kwargs):
        invocations.append(kwargs)
        return {"outcome": "response_received", "backend_valid": True, "text": json.dumps(next(outputs))}
    def dispatch(proposal, *, reserve):
        permit = reserve("a" * 64)  # Only after the native reviewed operation is fixed.
        writes.append((proposal, permit))
        return {"disposition": "response_received", "post_id": "reply", "reservation_id": permit["reservation_id"], "request_entered": True, "response_received": True}
    with PrivateExchange.create(tmp_path / "run") as store:
        budget = ready_budget(store)
        episode = Episode(room="room", source_id="source", parent_ids=("source", "decoy"))
        result = run_episode(episode, slot_id="s01", public_task="Synthetic handoff", budget=budget,
            invoke=invoke, read_source=lambda _: public_post("source", "room"),
            dispatch=dispatch, store=store, withhold_write_response=True)
        assert len(invocations) == 3 and len(writes) == 1
        assert writes[0][0]["body"].encode() == body.encode()
        assert "unknown_delivery" in invocations[2]["messages"][-1]["content"]
        assert result["claim"]["completion"] == "unknown"
        assert result["task_outcome"] == "not_evaluated"
        assert budget.summary()["reserved_generations"] == 5


def test_malformed_first_output_keeps_failed_episode_no_repair(tmp_path):
    with PrivateExchange.create(tmp_path / "run") as store:
        budget = ready_budget(store)
        def unused(*args, **kwargs):
            raise AssertionError("tool must not run")
        result = run_episode(Episode(room="r", source_id="s", parent_ids=("s",)),
            slot_id="s01", public_task="Task", budget=budget,
            invoke=lambda **_: {"outcome": "response_received", "backend_valid": True, "text": "not JSON"},
            read_source=unused, dispatch=unused, store=store)
        assert result["failure"] == "malformed_phase_1" and result["claim"] is None
        assert budget.summary()["reserved_generations"] == 3


def test_invoke_timeout_stops_campaign_and_no_write(tmp_path):
    with PrivateExchange.create(tmp_path / "run") as store:
        budget = ready_budget(store)
        def timeout(**_):
            raise TimeoutError()
        result = run_episode(Episode(room="r", source_id="s", parent_ids=("s",)),
            slot_id="s01", public_task="Task", budget=budget, invoke=timeout,
            read_source=lambda _: None, dispatch=lambda *a, **k: None, store=store)
        assert result["failure"] == "invocation_incomplete"
        assert budget.summary()["failed"]
        assert budget.summary()["completed_generations"] is None


def test_actor_never_receives_native_control_metadata(tmp_path):
    outputs = iter([{"action": "read_source", "source_id": "s"},
        {"action": "write_reply", "room": "r", "parent_id": "s", "body": "wrong"},
        {"completion": "success", "reason": "claim"}])
    messages = []
    def invoke(**kwargs):
        messages.append(kwargs["messages"])
        return {"outcome": "response_received", "backend_valid": True, "text": json.dumps(next(outputs))}
    def dispatch(proposal, *, reserve):
        permit = reserve("a" * 64)
        return {"disposition": "response_received", "post_id": "reply", "grant_ref": "synthetic-private-handle", "reservation_id": permit["reservation_id"], "request_entered": True, "response_received": True}
    with PrivateExchange.create(tmp_path / "run") as store:
        run_episode(Episode(room="r", source_id="s", parent_ids=("s",)), slot_id="s01",
            public_task="Task", budget=ready_budget(store), invoke=invoke,
            read_source=lambda _: {**public_post(), "gateway_token": "synthetic-source-control"}, dispatch=dispatch, store=store)
    assert "synthetic-private-handle" not in json.dumps(messages)
    assert "synthetic-source-control" not in json.dumps(messages)


def test_missing_backend_validity_never_executes_a_tool(tmp_path):
    reads = []
    with PrivateExchange.create(tmp_path / "run") as store:
        result = run_episode(Episode(room="r", source_id="s", parent_ids=("s",)),
            slot_id="s01", public_task="Task", budget=ready_budget(store),
            invoke=lambda **_: {"outcome": "response_received", "text": '{"action":"read_source","source_id":"s"}'},
            read_source=lambda source: reads.append(source), dispatch=lambda *a, **k: None, store=store)
        assert result["failure"] == "backend_rejected"
        assert reads == []


def test_post_ack_without_reservation_is_incomplete(tmp_path):
    outputs = iter([{"action": "read_source", "source_id": "s"},
        {"action": "write_reply", "room": "r", "parent_id": "s", "body": "wrong"},
        {"completion": "success", "reason": "claim"}])
    with PrivateExchange.create(tmp_path / "run") as store:
        budget = ready_budget(store)
        result = run_episode(Episode(room="r", source_id="s", parent_ids=("s",)), slot_id="s01",
            public_task="Task", budget=budget,
            invoke=lambda **_: {"outcome": "response_received", "backend_valid": True, "text": json.dumps(next(outputs))},
            read_source=lambda _: public_post(),
            dispatch=lambda *a, **k: {"disposition": "response_received", "post_id": "reply"}, store=store)
        assert result["failure"] == "tool_or_record_incomplete" and result["claim"] is None
        assert budget.summary()["reserved_writes"] == 0


def test_identity_rejected_response_never_becomes_actor_proposal(tmp_path):
    with PrivateExchange.create(tmp_path / "run") as store:
        budget = ready_budget(store)
        result = run_episode(Episode(room="r", source_id="s", parent_ids=("s",)),
            slot_id="s01", public_task="Task", budget=budget,
            invoke=lambda **_: {"outcome": "response_received", "backend_valid": False,
                "text": '{"action":"read_source","source_id":"s"}', "failure": "MalformedBackendOutput"},
            read_source=lambda _: (_ for _ in ()).throw(AssertionError("must not read")),
            dispatch=lambda *a, **k: None, store=store)
        assert result["failure"] == "backend_rejected"
        assert budget.failed
