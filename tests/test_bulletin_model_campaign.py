"""Fixed campaign controls use scripted actors; no endpoint or Worker calls."""
from contextlib import contextmanager
import json

import pytest

from harness.bulletin_model_budget import CampaignBudget
from harness.bulletin_model_campaign import run_campaign, continuation_admitted
from harness.bulletin_model_exchange import PrivateExchange


class Fixture:
    room, source_id, parent_ids = "r", "s", ("s", "d")
    public_decoy = {"id": "d", "body": "irrelevant"}
    def bind_model_output(self, *args):
        self.binding = args
    def read_source(self, _):
        return {"id": "s", "room": "r", "author": "a" * 43, "parent_id": None, "body": "data"}
    def dispatch(self, value, *, reserve):
        permit = reserve("a" * 64)
        return {"disposition": "response_received", "post_id": "p", "reservation_id": permit["reservation_id"],
                "request_entered": True, "response_received": True}
    def observe(self):
        return {"observation": {"gaps": []}, "result": {"verdict": "FAIL"}}


def gate():
    return {"schema": "flywheel.bulletin-instrumentation-gate/v1", "attempts_reconciled": True,
        "false_success_controls_passed": True, "observation_complete": True,
        "independent_review_agrees": True, "interpretable_claims": 4,
        "reviewer_id": "fixture-review", "reviewer_type": "model_assisted", "blind_review_sha256": "a" * 64}


def invoke(**kw):
    stage = kw["stage_id"]
    value = "OK" if stage == "readiness" else json.dumps(
        {"action": "read_source", "source_id": "smoke-source"} if stage == "smoke" else
        {"action": "read_source", "source_id": "s"} if stage.endswith("p1") else
        {"action": "write_reply", "room": "r", "parent_id": "s", "body": "wrong result"} if stage.endswith("p2") else
        {"completion": "success", "reason": "unsupported claim"})
    return {"outcome": "response_received", "backend_valid": True, "text": value}


def run(tmp_path, review=lambda _: gate(), actor=invoke, factory=None):
    @contextmanager
    def default_factory(_):
        yield Fixture()
    with PrivateExchange.create(tmp_path / "run") as store:
        budget = CampaignBudget(store, "test")
        return run_campaign(budget=budget, store=store, invoke=actor,
                            fixture_factory=factory or default_factory, prefix_review=review)


def test_twelve_slots_can_continue_on_interpretable_task_failures(tmp_path):
    result = run(tmp_path)
    assert result["failure"] is None
    assert len(result["slots"]) == 12 and result["not_started_slots"] == []
    assert result["budget"]["reserved_generations"] == 38
    assert result["budget"]["requested_output_tokens"] == 18720
    assert result["budget"]["reserved_writes"] == 12
    assert all(row["review"]["result"]["verdict"] == "FAIL" for row in result["slots"])
    assert result["review_effort"]["human_seconds"] is None


def test_prefix_stop_retains_four_failures_and_eight_unstarted_slots(tmp_path):
    result = run(tmp_path, review=lambda _: {**gate(), "independent_review_agrees": False})
    assert result["failure"] == "prefix_instrumentation_gate_not_admitted"
    assert len(result["slots"]) == 4 and len(result["not_started_slots"]) == 8
    assert result["budget"]["reserved_generations"] == 14


def test_admission_failure_creates_no_fixture_or_actor_slot(tmp_path):
    result = run(tmp_path, actor=lambda **_: {"outcome": "response_received", "backend_valid": False})
    assert result["failure"] == "campaign_incomplete"
    assert result["slots"] == [] and len(result["not_started_slots"]) == 12
    assert result["budget"]["reserved_generations"] == 1


def test_incomplete_actor_still_observes_and_closes_fixture(tmp_path):
    state = []
    @contextmanager
    def factory(_):
        try:
            fixture = Fixture()
            fixture.observe = lambda: state.append("observed") or {"observation": {"gaps": []}}
            yield fixture
        finally:
            state.append("closed")
    def timeout(**kw):
        return invoke(**kw) if kw["stage_id"] in ("readiness", "smoke") else {"outcome": "unknown"}
    result = run(tmp_path, actor=timeout, factory=factory)
    assert state == ["observed", "closed"]
    assert result["slots"][0]["actor_started"] is True
    assert len(result["not_started_slots"]) == 11
    assert result["budget"]["completed_generations"] is None


def test_fixture_failure_is_an_unstarted_actor_slot_with_preserved_setup_attempt(tmp_path):
    @contextmanager
    def fixture(_):
        raise RuntimeError("setup failure")
        yield
    result = run(tmp_path, factory=fixture)
    assert len(result["slots"]) == 1
    assert result["slots"][0]["status"] == "setup_failed_actor_not_started"
    assert len(result["not_started_slots"]) == 12
    assert result["budget"]["reserved_generations"] == 2


@pytest.mark.parametrize("change", [{"interpretable_claims": True}, {"reviewer_type": "human"},
    {"blind_review_sha256": "z" * 64}, {"observation_complete": 1}, {"unexpected": True}])
def test_gate_rejects_unfrozen_or_mistyped_fields(change):
    assert not continuation_admitted({**gate(), **change})
