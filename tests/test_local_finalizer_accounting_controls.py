"""Independent failure controls for receipt coverage and transport meaning."""
import copy
import uuid
from types import SimpleNamespace

import pytest

from harness.local_finalizer_accounting import ExperimentAccounting, digest, AccountingDurabilityError
from harness.local_finalizer_accounting_verify import aggregate_accounting
from harness.observed_proposer import ObservedProposer
from harness.local_finalizer_transport_accounting import transport_counts
from harness.local_finalizer_experiment import FIXED_PARAMS, run_candidate_prefix_experiment
from test_local_finalizer_accounting import task, run, invoke


def prepared(tmp_path, factory=None):
    account = ExperimentAccounting(transport_factory=factory)
    account.prepare(tmp_path, [task()], {"repetitions": 1}, "c" * 64)
    return account, account.stage("one", "normal")


def finish(account, stage):
    stage.finish("returned", eligible=False, result_state="returned")
    account.skip("one", "A", "skipped_candidate_ineligible")
    account.skip("one", "B", "skipped_candidate_ineligible")
    return account.finalize()


def factory(mode):
    def make(*, observer):
        def transport(*args):
            if mode == "preflight":
                exc = OSError("denied")
                exc.code, exc.terminal_event = "route_not_allowed", None
                raise exc
            repeats = 2 if mode == "retry" else 1
            for i in range(repeats):
                base = {"attempt_id": str(uuid.uuid4()), "method": "POST", "path": "/api/chat",
                        "connection_started": False, "request_send_started": False,
                        "outcome": None, "code": None, "status": None}
                observer({**base, "phase": "connection_attempt"})
                observer({**base, "phase": "request_send_started", "connection_started": True})
                if mode == "intent_only":
                    raise OSError("lost after intent")
                failed = i < repeats - 1 or mode == "timeout"
                observer({**base, "phase": "terminal", "connection_started": True,
                    "request_send_started": True, "outcome": "timeout" if failed else "response",
                    "code": "deadline_exceeded" if failed else "response_received",
                    "status": None if failed else 200})
            if mode == "timeout":
                raise TimeoutError("timeout")
            return 200, {}
        return transport
    return make


@pytest.mark.parametrize("mode,expected", [("retry", 2), ("timeout", 1), ("preflight", 0), ("intent_only", None)])
def test_retry_send_intent_preflight_and_unknown_boundaries(tmp_path, mode, expected):
    account, stage = prepared(tmp_path, factory(mode))
    stage.enter()
    backend = SimpleNamespace()
    stage.attach(backend)

    class Proposer:
        model_ref = "fake"
        def generate(self, *args, **kwargs):
            backend.transport("POST", "http://127.0.0.1:1/api/chat", b"{}", 1)
            return SimpleNamespace(usage={"eval_count": 3}, served_model="fake", model_ref="fake")

    tracked = ObservedProposer(Proposer(), 60, lambda: 0, observer=stage)
    try:
        tracked.generate("private", max_new_tokens=16)
    except OSError:
        pass
    result = finish(account, stage)
    assert result["total_started_invocations"] == 1
    assert result["request_send_attempts"] == expected
    assert result["native_usage"]["eval_count"]["total"] == (3 if mode == "retry" else None)


def rehash(receipt):
    for event in receipt["events"]:
        event["event_id"] = digest({k: v for k, v in event.items() if k != "event_id"})
    receipt["events_sha256"] = digest(receipt["events"])


@pytest.mark.parametrize("mutation", ["orphan", "gap", "unknown_stage", "contradictory_duplicate"])
def test_hash_valid_malformed_receipts_are_not_complete(tmp_path, mutation):
    _, account = run(tmp_path)
    receipts = copy.deepcopy(account.receipts())
    events = receipts[0]["events"]
    if mutation == "orphan":
        next(e for e in events if e["kind"] == "invocation_terminal")["invocation_id"] = "f" * 64
    elif mutation == "gap":
        next(e for e in events if e["kind"] == "invocation_started")["ordinal"] = 2
    elif mutation == "unknown_stage":
        receipts[0]["stage_id"] = "f" * 64
    else:
        extra = copy.deepcopy(receipts[0])
        extra["disposition"] = "raised"
        receipts.append(extra)
    rehash(receipts[0])
    with pytest.raises(ValueError):
        aggregate_accounting(account.manifest, receipts)


def test_truncated_stream_and_missing_usage_stay_unknown(tmp_path):
    account, stage = prepared(tmp_path)
    stage.enter()
    invoke(stage, usage={"eval_count": True, "prompt_eval_count": 4, "secret": "never retain"})
    result = finish(account, stage)
    assert result["native_usage"]["eval_count"]["total"] is None
    assert result["native_usage"]["prompt_eval_count"]["total"] == 4
    receipt = copy.deepcopy(account.receipts()[0])
    receipt["events"] = receipt["events"][:-2]
    rehash(receipt)
    result = aggregate_accounting(account.manifest, [receipt, *account.receipts()[1:]])
    assert result["known_started_invocations"] == 1
    assert result["total_started_invocations"] is None


def test_terminal_sink_failure_stops_next_invocation(tmp_path, monkeypatch):
    account, stage = prepared(tmp_path)
    stage.enter()
    stage.instrument()
    append = stage._append
    def fail_terminal(event):
        if event["kind"] == "invocation_terminal":
            raise OSError("disk")
        append(event)
    monkeypatch.setattr(stage, "_append", fail_terminal)
    with pytest.raises(AccountingDurabilityError):
        invoke(stage, count=2)
    assert stage.invocations == 1
    with pytest.raises(AccountingDurabilityError):
        account.dispatch("one", "A", lambda: pytest.fail("no later callback"))


def transport_records(phases, *, outcome="error", connected=False, sent=False, status=None):
    parent, call = "logical", "call"
    base = {"attempt_id": str(uuid.uuid4()), "method": "POST", "path": "/api/chat",
            "connection_started": False, "request_send_started": False,
            "outcome": None, "code": None, "status": None}
    events = [{"kind": "transport_observation_started"},
              {"kind": "transport_callable_started", "invocation_id": parent, "call_id": call}]
    for phase in phases:
        record = {**base, "phase": phase}
        if phase == "request_send_started":
            record["connection_started"] = True
        if phase == "terminal":
            record.update(connection_started=connected, request_send_started=sent,
                          outcome=outcome, code="response_received" if outcome == "response" else "deadline_exceeded",
                          status=status)
        events.append({"kind": "transport", "invocation_id": parent, "call_id": call, "transport": record})
    events.append({"kind": "transport_callable_terminal", "invocation_id": parent,
                   "call_id": call, "preflight_no_io": False})
    return events, {parent: {}}


def test_terminal_before_first_connection_is_known_no_io():
    events, starts = transport_records(["terminal"], outcome="timeout")
    complete, sends, connections, responses, _ = transport_counts(events, starts)
    assert (complete, sends, connections, responses) == (True, 0, 0, 0)


@pytest.mark.parametrize("phases,outcome,connected,sent,status", [
    (["connection_attempt", "terminal"], "response", False, False, 200),
    (["connection_attempt", "request_send_started", "terminal"], "response", True, True, None),
    (["connection_attempt", "request_send_started", "terminal"], "error", True, True, 200),
    (["connection_attempt", "request_send_started", "terminal"], "error", False, False, None),
])
def test_contradictory_transport_progression_refused(phases, outcome, connected, sent, status):
    events, starts = transport_records(phases, outcome=outcome, connected=connected, sent=sent, status=status)
    with pytest.raises(ValueError):
        transport_counts(events, starts)


@pytest.mark.parametrize("future", [False, True])
def test_systemic_skip_requires_actual_prior_stop_policy(tmp_path, future):
    _, account = run(tmp_path, [task("one"), task("two")])
    receipts = copy.deepcopy(account.receipts())
    cause = next(r for r in receipts if r["task_id"] == ("two" if future else "one") and r["stage"] == "A")
    skipped = next(r for r in receipts if r["task_id"] == ("one" if future else "two") and r["stage"] == "A")
    cause["events"][-1]["result_state"] = "transport_error" if future else "context_not_admitted"
    rehash(cause)
    skipped["disposition"] = "skipped_systemic_arm_block"
    skipped["events"] = [{"kind": "stage_disposition", "seq": 0, "stage_id": skipped["stage_id"],
                          "disposition": skipped["disposition"], "caused_by": cause["stage_id"]}]
    rehash(skipped)
    with pytest.raises(ValueError):
        aggregate_accounting(account.manifest, receipts)


def test_actual_systemic_failure_keeps_prefix_work_and_skips_later_arm(tmp_path):
    context = ExperimentAccounting()
    entered = []
    def candidate(item, *args):
        invoke(context.stage(item["task_id"], "normal"))
        return {"state": "returned", "eligible": True, "selected_text": "same"}
    def finalizer(arm, item, *args):
        entered.append((item["task_id"], arm))
        invoke(context.stage(item["task_id"], arm))
        return {"state": "transport_error" if arm == "A" else "returned", "selected_text": "same"}
    result = run_candidate_prefix_experiment([task("one"), task("two")], tmp_path / "run", FIXED_PARAMS,
        candidate_runner=candidate, finalizer_runner=finalizer, score_runner=lambda *a: ("pass", []),
        accounting=context)
    assert entered == [("one", "A"), ("one", "B"), ("two", "B")]
    assert result["invocation_accounting"]["total_started_invocations"] == 5
    assert context.stage("two", "A").receipt["disposition"] == "skipped_systemic_arm_block"
