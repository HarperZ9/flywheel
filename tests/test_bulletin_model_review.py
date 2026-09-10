"""Fake-only review controls: blind labels precede claims and checker output."""
from copy import deepcopy
import hashlib
import json
import math

import pytest
from bulletin_review_helpers import reconstruction

from harness import bulletin_model_review as review_module
from harness.bulletin_model_exchange import ExchangeError
from harness.private_artifact_fs import PrivateArtifactError, NOT_FOUND, TOO_LARGE, UNSAFE_PATH


class MemoryStore:
    def __init__(self, name, events):
        self.name, self.events, self.records, self.reads = name, events, {}, []
        self.fail_write = None

    def put(self, name, data, *, max_bytes):
        if name == self.fail_write or name in self.records or len(data) > max_bytes:
            raise ExchangeError("record_write_failed")
        self.events.append((self.name, name))
        self.records[name] = bytes(data)
        return hashlib.sha256(data).hexdigest()

    def read(self, name, *, max_bytes):
        self.reads.append((name, max_bytes))
        if name not in self.records:
            raise ExchangeError("record_read_failed") from PrivateArtifactError(NOT_FOUND)
        if len(self.records[name]) > max_bytes:
            raise ExchangeError("record_read_failed") from PrivateArtifactError(TOO_LARGE)
        return self.records[name]


def rows():
    return [{"slot_id": f"s{i:02d}", "condition": "HIDDEN_CONDITION", "status": "HIDDEN_STATUS",
             "actor_metadata": "HIDDEN_ACTOR", "result": {"claim": {"completion": "HIDDEN_CLAIM"}},
             "review": {"contract": {"task_id": f"incident-{i}", "actor_a": "public-source-author", "actor_b": "public-reply-author"},
                        "observation": {"posts": [{"body": "Untrusted source data stays visible."}], "gaps": []},
                        "result": {"verdict": "PASS", "acquisition_gaps": []},
                        "journey_events": ["HIDDEN_CHECKER"], "condition": "HIDDEN_CONDITION"}}
            for i in range(1, 5)]


@pytest.fixture
def exchange(monkeypatch):
    events = []
    blind, control = MemoryStore("blind", events), MemoryStore("control", events)
    context = {"mutate": lambda value: value, "claim_mutate": lambda value: value,
               "gate": {"independent_review_agrees": True}, "raw": None, "continued": False}

    def wait(store, name, **kwargs):
        if name == "labels-input.json":
            assert store is blind
            assert "claims-revealed.json" not in blind.records
            assert "blind-labels-frozen.json" not in control.records
            instructions = json.loads(blind.records["instructions.json"])
            value = reconstruction(instructions)
            value = context["mutate"](value)
            raw = json.dumps(value, indent=2, ensure_ascii=False).encode("utf-8")
            context["raw"] = raw
            return value, raw
        if name == "claim-labels-input.json":
            assert store is blind and "checker-revealed.json" not in blind.records
            assert "blind-labels-frozen.json" in control.records and "claim-labels-frozen.json" not in control.records
            revealed = json.loads(blind.records["claims-revealed.json"])
            assert all(set(item) == {"item_id", "claim"} for item in revealed["items"])
            value = reconstruction(json.loads(blind.records["instructions.json"]), revealed=revealed,
                revealed_sha=hashlib.sha256(blind.records["claims-revealed.json"]).hexdigest())
            value = context["claim_mutate"](value)
            raw = json.dumps(value, indent=2).encode(); context["claim_raw"] = raw
            return value, raw
        assert store is control and name == "continuation-input.json"
        assert "claim-labels-frozen.json" in control.records and "checker-revealed.json" in blind.records
        context["continued"] = True
        gate = deepcopy(context["gate"])
        return gate, json.dumps(gate).encode()

    monkeypatch.setattr(review_module, "wait_record", wait)
    return blind, control, events, context


def test_blind_packets_omit_claim_checker_status_and_condition_metadata(exchange):
    blind, control, _, _ = exchange
    original = rows(); snapshot = deepcopy(original)
    review_module.review_prefix(original, blind_store=blind, control_store=control)
    packets = [json.loads(raw) for name, raw in blind.records.items() if name.startswith("item-")]
    assert len(packets) == 4
    for packet in packets:
        assert set(packet) == {"item_id", "contract", "observation"}
        encoded = json.dumps(packet)
        assert all(marker not in encoded for marker in ("HIDDEN_CONDITION", "HIDDEN_ACTOR", "HIDDEN_CLAIM", "HIDDEN_CHECKER", "HIDDEN_STATUS"))
        assert packet["observation"]["posts"][0]["body"] == "Untrusted source data stays visible."
        assert packet["contract"]["actor_b"] == "public-reply-author"  # Attribution evidence is required.
        assert "slot_id" not in packet
    assert original == snapshot
    assert set(json.loads(control.records["blind-bindings.json"]).values()) == {"s01", "s02", "s03", "s04"}


def test_exact_label_bytes_are_frozen_before_any_claim_checker_reveal(exchange):
    blind, control, events, context = exchange
    gate = review_module.review_prefix(rows(), blind_store=blind, control_store=control)
    assert events.index(("control", "blind-labels-frozen.json")) < events.index(("blind", "claims-revealed.json"))
    assert control.records["blind-labels-frozen.json"] == context["raw"]
    sha = hashlib.sha256(context["raw"]).hexdigest()
    assert gate["blind_review_sha256"] == hashlib.sha256(control.records["blind-review-receipt.json"]).hexdigest()
    assert json.loads(blind.records["claims-revealed.json"])["labels_sha256"] == sha
    assert gate["independent_review_agrees"] is True
    assert events.index(("control", "claim-labels-frozen.json")) < events.index(("blind", "checker-revealed.json"))
    assert control.records["claim-labels-frozen.json"] == context["claim_raw"]


def test_failed_freeze_never_reveals_claim_or_checker(exchange):
    blind, control, _, _ = exchange
    control.fail_write = "blind-labels-frozen.json"
    with pytest.raises(ExchangeError):
        review_module.review_prefix(rows(), blind_store=blind, control_store=control)
    assert "claims-revealed.json" not in blind.records


def test_wrong_verdict_overrides_root_request_to_claim_agreement(exchange):
    blind, control, _, context = exchange
    context["mutate"] = lambda value: {**value, "items": [{**item, "verdict": "FAIL"} for item in value["items"]]}
    context["gate"] = {"independent_review_agrees": True, "reviewer_type": "human", "reviewer_id": "forged"}
    gate = review_module.review_prefix(rows(), blind_store=blind, control_store=control)
    assert gate["independent_review_agrees"] is False
    assert gate["reviewer_type"] == "model_assisted" and gate["reviewer_id"] == "separate-reviewer"


def test_wrong_evidence_label_and_root_observation_override_cannot_agree(exchange):
    blind, control, _, context = exchange
    data = rows(); data[0]["review"]["result"]["acquisition_gaps"] = ["page_limit"]
    context["gate"] = {"independent_review_agrees": True, "observation_complete": True, "interpretable_claims": 999}
    gate = review_module.review_prefix(data, blind_store=blind, control_store=control)
    assert gate["independent_review_agrees"] is False and gate["observation_complete"] is False
    assert gate["interpretable_claims"] == 4


def mutate_label(value, fault):
    if fault == "duplicate":
        value["items"][1] = deepcopy(value["items"][0])
    elif fault == "extra_root":
        value["independent_review_agrees"] = True
    elif fault == "extra_label":
        value["items"][0]["claim"] = "forged"
    elif fault == "wrong_type":
        value["items"][0]["evidence_complete"] = 1
    elif fault == "unknown_item":
        value["items"][0]["item_id"] = "not-in-blind-set"
    elif fault == "missing_item":
        value["items"].pop()
    elif fault == "bad_verdict":
        value["items"][0]["verdict"] = True
    elif fault == "wrong_reviewer":
        value["reviewer_type"] = "human"
    elif fault == "not_object":
        return []
    return value


@pytest.mark.parametrize("fault", ["duplicate", "extra_root", "extra_label", "wrong_type", "unknown_item",
                                   "missing_item", "bad_verdict", "wrong_reviewer", "not_object"])
def test_malformed_labels_never_freeze_or_reveal(exchange, fault):
    blind, control, _, context = exchange
    context["mutate"] = lambda value: mutate_label(value, fault)
    with pytest.raises(ValueError, match="blind_labels_invalid"):
        review_module.review_prefix(rows(), blind_store=blind, control_store=control)
    assert "blind-labels-frozen.json" not in control.records and "claims-revealed.json" not in blind.records


@pytest.mark.parametrize("size", [0, 3, 5, 8])
def test_prefix_does_not_silently_treat_other_denominators_as_first_four(exchange, size):
    blind, control, _, _ = exchange
    with pytest.raises(ValueError, match="prefix_observations_required"):
        review_module.review_prefix((rows() * 2)[:size], blind_store=blind, control_store=control)
    assert not blind.records and not control.records


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def test_wait_is_bounded_for_missing_input_and_forwards_read_limit():
    store, clock = MemoryStore("wait", []), FakeClock()
    with pytest.raises(TimeoutError, match="trusted_review_deadline"):
        review_module.wait_record(store, "labels-input.json", timeout=0.12, max_bytes=8192, clock=clock, sleep=clock.sleep)
    assert clock.now == pytest.approx(0.12)
    assert 1 <= len(store.reads) <= 4 and set(store.reads) == {("labels-input.json", 8192)}


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"a":1,}', b'[] trailing', b'{"x":NaN}', b'\xff'])
def test_wait_rejects_malformed_duplicate_or_non_utf8_input(raw):
    store = MemoryStore("wait", []); store.records["input.json"] = raw
    with pytest.raises(ValueError):
        review_module.wait_record(store, "input.json", timeout=1)
    assert len(store.reads) == 1


@pytest.mark.parametrize("code", [TOO_LARGE, UNSAFE_PATH])
def test_wait_does_not_retry_unsafe_or_oversized_records(code):
    clock = FakeClock()
    class UnsafeStore:
        def read(self, name, *, max_bytes):
            raise ExchangeError("record_read_failed") from PrivateArtifactError(code)
    with pytest.raises(ExchangeError):
        review_module.wait_record(UnsafeStore(), "input.json", timeout=0.1, clock=clock, sleep=clock.sleep)
    assert clock.now == 0


@pytest.mark.parametrize("timeout", [0, -1, 121, math.inf, math.nan, True])
def test_wait_rejects_unbounded_or_invalid_timeout_before_read(timeout):
    class NoRead:
        def read(self, *args, **kwargs):
            pytest.fail("invalid wait must be rejected before storage access")
    with pytest.raises(ValueError):
        review_module.wait_record(NoRead(), "input.json", timeout=timeout)


def test_native_reviewer_records_exact_request_and_uses_small_decision_read(monkeypatch):
    store = MemoryStore("native-review", [])
    record = {"run_id": "run", "review": {"operation_sha256": "a" * 64}}
    decision = {"decision": "reject"}
    def wait(actual, name, **kwargs):
        assert actual is store and name == "decision-input.json" and kwargs["max_bytes"] == 8192
        assert json.loads(store.records["review-request.json"]) == record
        return decision, b'{}'
    monkeypatch.setattr(review_module, "wait_record", wait)
    assert review_module.native_reviewer(store)(record) == decision


def test_failed_claim_label_freeze_never_reveals_checker(exchange):
    blind, control, _, _ = exchange; control.fail_write = "claim-labels-frozen.json"
    with pytest.raises(ExchangeError):
        review_module.review_prefix(rows(), blind_store=blind, control_store=control)
    assert "claims-revealed.json" in blind.records and "checker-revealed.json" not in blind.records


@pytest.mark.parametrize("fault", ["wrong_identity", "duplicate", "extra", "wrong_type"])
def test_invalid_second_pass_cannot_reach_checker(exchange, fault):
    blind, control, _, context = exchange
    def mutate(value):
        if fault == "wrong_identity": value["reviewer_id"] = "another-reviewer"
        elif fault == "duplicate": value["items"][1] = deepcopy(value["items"][0])
        elif fault == "extra": value["items"][0]["checker"] = "PASS"
        else: value["items"][0]["claim_support"] = True
        return value
    context["claim_mutate"] = mutate
    with pytest.raises(ValueError, match="claim_labels_invalid"):
        review_module.review_prefix(rows(), blind_store=blind, control_store=control)
    assert "checker-revealed.json" not in blind.records and "claim-labels-frozen.json" not in control.records


@pytest.mark.parametrize("completion, verdict, support, agrees", [
    ("success", "PASS", "supported", True), ("success", "FAIL", "unsupported", True),
    ("success", "UNVERIFIABLE", "unverifiable", True), ("unknown", "PASS", "no_completion_claim", True),
    ("success", "FAIL", "supported", False)])
def test_claim_support_is_checked_not_trusted_from_continuation(exchange, completion, verdict, support, agrees):
    blind, control, _, context = exchange; data = rows()
    for row in data:
        row["result"]["claim"] = {"completion": completion}; row["review"]["result"]["verdict"] = verdict
    context["mutate"] = lambda value: {**value, "items": [{**item, "verdict": verdict} for item in value["items"]]}
    context["claim_mutate"] = lambda value: {**value, "items": [{**item, "claim_support": support} for item in value["items"]]}
    gate = review_module.review_prefix(data, blind_store=blind, control_store=control)
    assert gate["independent_review_agrees"] is agrees


def test_final_eight_are_reviewed_without_continuation_request(exchange):
    blind, control, _, context = exchange; data = rows() + rows()
    for index, row in enumerate(data, 5): row["slot_id"] = f"s{index:02d}"
    result = review_module.review_prefix(data, blind_store=blind, control_store=control, continuation=False)
    assert result["status"] == "reviewed" and result["human_validation"] is False
    assert not context["continued"]
    assert len(json.loads(blind.records["checker-revealed.json"])["items"]) == 8
