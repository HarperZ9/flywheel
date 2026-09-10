"""Native IPC tests use fake owned processes, never Flutter or a gateway."""
import hashlib
import json
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from harness.bulletin_model_exchange import PrivateExchange, ExchangeError
from harness.bulletin_model_native import NativeCoordinator, NativeLaunch, NativeError, NativeRecordingError
from harness.evidence_json import canonical_bytes, canonical_sha256
from harness.gateway_operation import canonicalize_operation


def digest(value):
    return hashlib.sha256(value).hexdigest()


def review_for(launch, action, proposal_sha):
    op = {"name": "bulletin", "tool": "board_write_post", "governance_tier": "T2", "timeout": 20,
          "bulletin_base_url": launch.bulletin_origin,
          "args": {k: action[k] for k in ("room", "body", "parent_id")}, "data_refs": [],
          "credential_refs": ["cred_" + "c" * 32]}
    operation = canonicalize_operation("lane.call", op)
    review = {"schema": "flywheel.gateway-grant-review/v1", "proposal_ref": "prp_" + "a" * 32,
              "planned_grant_ref": "gnt_" + "b" * 32, "record_sha256": "e" * 64,
              "operation_ref": "op_" + "d" * 32, "action": "lane.call", "journey_ref": "jrn_" + "a" * 32,
              "expected_event_head": "b" * 64, "client_request_id": launch.request_id,
              "destination": dict(operation.destination), "tool": operation.tool,
              "scopes": list(operation.scopes), "data_refs": [], "credential_refs": op["credential_refs"],
              "execution_plan_sha256": "f" * 64, "operation_sha256": operation.operation_sha256,
              "arguments_sha256": operation.arguments_sha256, "operation": op,
              "expires_at": "2099-01-01T00:00:00Z"}
    review["review_sha256"] = canonical_sha256(review)
    return {"schema_version": 1, "run_id": launch.run_id, "slot_id": launch.slot_id,
            "proposal_sha256": proposal_sha, "review": review}


def decision(record, decision="approve"):
    r = record["review"]
    return {**{k: record[k] for k in ("schema_version", "run_id", "slot_id", "proposal_sha256")},
            "review_sha256": r["review_sha256"], "operation_sha256": r["operation_sha256"],
            "proposal_ref": r["proposal_ref"], "reviewer_id": "trusted-reviewer",
            "reviewer_type": "assistant_supervisor", "decision": decision, "duration_ms": 0}


class FakeProcess:
    def __init__(self, exchange, launch):
        self.exchange, self.launch = exchange, launch
        self.resumed = self.closed = self.reviewed = self.result_written = False
        self.ready = b"BULLETIN_ACTOR_READY\n"
        self.fault = None

    def resume(self):
        self.resumed = True
        if self.ready is not None:
            self.exchange.put("ready.txt", self.ready, max_bytes=64)
        return True

    def wait(self, timeout_s):
        if self.closed or self.fault == "exit":
            return SimpleNamespace(returncode=1, stdout="fake stdout", stderr="fake native startup failure",
                                   elapsed_ms=1, timed_out=False, malformed_output=False)
        try:
            raw = self.exchange.read("proposal.json", max_bytes=8192)
            proposal = json.loads(raw)
        except ExchangeError:
            return None
        if not self.reviewed:
            record = review_for(self.launch, proposal["proposal"], digest(raw))
            if self.fault == "review":
                record["slot_id"] = "wrong-slot"
            if self.fault == "bool_schema":
                record["schema_version"] = True
            if self.fault == "extra_review":
                record["review"]["extra"] = "unapproved-field"
                record["review"]["review_sha256"] = canonical_sha256({k: v for k, v in record["review"].items() if k != "review_sha256"})
            self.exchange.put("review.json", canonical_bytes(record), max_bytes=65536)
            self.reviewed = True
        try:
            value = json.loads(self.exchange.read("decision.json", max_bytes=8192))
            rejected = value["decision"] == "reject"
            permit = None if rejected else json.loads(self.exchange.read("dispatch-permit.json", max_bytes=8192))
        except ExchangeError:
            return None
        if self.fault == "missing_result":
            return SimpleNamespace(returncode=1, stdout="fake stdout", stderr="fake native startup failure",
                                   elapsed_ms=1, timed_out=False, malformed_output=False)
        if not self.result_written:
            result = {"schema_version": 1, "run_id": self.launch.run_id, "slot_id": self.launch.slot_id,
                      "proposal_sha256": digest(raw), "reservation_id": None if rejected else permit["reservation_id"],
                      "stage": "reject" if rejected else "dispatch", "disposition": "rejected" if rejected else "response_received",
                      "request_entered": not rejected, "response_received": not rejected,
                      "post_id": None if rejected else "persisted-reply", "error_code": None}
            if self.fault == "result":
                result["reservation_id"] = "other-reservation"
            if self.fault == "recording":
                result["error_code"] = "native_recording_failed"
            if self.fault == "contradiction":
                result["error_code"] = "native_driver_incomplete"
            self.exchange.put("result.json", canonical_bytes(result), max_bytes=16384)
            self.result_written = True
        return None

    def close(self):
        self.closed = True


@pytest.fixture
def native(tmp_path):
    files = {}
    for name in ("dart", "snapshot", "packages", "config"):
        files[name] = tmp_path / name
        files[name].write_bytes(b"fixture")
    config = {"mode": "actual_worker_loopback", "token": "PRIVATE_TOKEN", "journey_ref": "jrn_" + "a" * 32,
              "event_head": "b" * 64, "credential_ref": "cred_" + "c" * 32,
              "base_url": "http://127.0.0.1:12345", "bulletin_base_url": "http://127.0.0.1:12346"}
    raw = canonical_bytes(config); files["config"].write_bytes(raw)
    launch = NativeLaunch(dart=files["dart"], flutter_snapshot=files["snapshot"], flutter_packages=files["packages"],
                          desktop_root=tmp_path, fixture_config=files["config"], fixture_config_sha256=digest(raw),
                          manifest_sha256="1" * 64, run_id="run", slot_id="s01", room="scratch", parent_ids=("source", "decoy"),
                          request_id="request", gateway_origin=config["base_url"], bulletin_origin=config["bulletin_base_url"],
                          setup_seconds=5, active_seconds=5, review_seconds=1)
    with PrivateExchange.create(tmp_path / "ipc") as exchange:
        process = FakeProcess(exchange, launch)
        calls = []
        def factory(argv, **kwargs):
            calls.append((argv, kwargs)); return process
        coordinator = NativeCoordinator(exchange, launch=launch, reviewer=decision, process_factory=factory)
        yield coordinator, exchange, process, calls
        coordinator.close()


ACTION = {"action": "write_reply", "room": "scratch", "parent_id": "source", "body": ' {"task_id":"wrong", "state":"closed"}  '}


def bind(coordinator):
    coordinator.prestart()
    coordinator.bind_model_output("run-s01-p2", canonical_bytes(ACTION))


def test_exact_proposal_bound_review_reservation_and_result(native):
    c, exchange, process, calls = native
    assert c.remaining_active_seconds() == 0
    bind(c)
    assert 0 < c.remaining_active_seconds() <= 5
    def reserve(sha):
        with pytest.raises(ExchangeError):
            exchange.read("dispatch-permit.json", max_bytes=8192)
        return {"reservation_id": "run-s01-write", "slot_id": "s01", "operation_sha256": sha}
    result = c.dispatch(ACTION, reserve=reserve)
    assert result["disposition"] == "response_received" and result["post_id"] == "persisted-reply"
    proposal = json.loads(exchange.read("proposal.json", max_bytes=8192))
    assert proposal["proposal"]["body"] == ACTION["body"]  # Wrong semantics intentionally survive.
    assert calls[0][0][0] == str(c.launch.dart)
    assert "--no-pub" in calls[0][0] and calls[0][1]["stdin_bytes"] == b""
    assert calls[0][1]["env"]["FLUTTER_SUPPRESS_ANALYTICS"] == "true"
    assert calls[0][1]["env"]["CI"] == "true"
    assert "PRIVATE_TOKEN" not in str(calls)
    assert process.closed
    assert c.remaining_active_seconds() == 0
    with pytest.raises(NativeError):
        c.dispatch(ACTION, reserve=reserve)


def test_reject_does_not_reserve(native):
    c, exchange, _, _ = native; c.reviewer = lambda record: decision(record, "reject")
    bind(c)
    result = c.dispatch(ACTION, reserve=lambda _: pytest.fail("reserved rejected operation"))
    assert result["disposition"] == "rejected" and result["reservation_id"] is None
    with pytest.raises(ExchangeError):
        exchange.read("dispatch-permit.json", max_bytes=8192)


@pytest.mark.parametrize("fault", ["review", "result", "recording", "bool_schema", "extra_review", "contradiction"])
def test_corrupt_binding_and_recording_failure_latch(native, fault):
    c, _, process, _ = native; process.fault = fault; bind(c)
    with pytest.raises(NativeRecordingError):
        c.dispatch(ACTION, reserve=lambda sha: {"reservation_id": "run-s01-write", "slot_id": "s01", "operation_sha256": sha})
    assert c.failed and process.closed


def test_unknown_delivery_keeps_consumed_reservation(native):
    c, _, process, _ = native; process.fault = "missing_result"; bind(c)
    result = c.dispatch(ACTION, reserve=lambda sha: {"reservation_id": "run-s01-write", "slot_id": "s01", "operation_sha256": sha})
    assert result["disposition"] == "unknown_delivery" and result["reservation_id"] == "run-s01-write"
    assert result["request_entered"] is None and result["response_received"] is None


@pytest.mark.parametrize("ready", [b"READY\n", None])
def test_only_exact_file_sentinel_admits_ready(native, ready):
    c, _, process, _ = native; process.ready = ready
    if ready is None:
        c.launch = replace(c.launch, setup_seconds=0.05)
    with pytest.raises(NativeError):
        c.prestart()
    assert process.closed


def test_reservation_failure_never_publishes_permit(native):
    c, exchange, process, _ = native; bind(c)
    def fail(_):
        raise OSError("secret ledger error")
    with pytest.raises(NativeRecordingError, match="native_recording_failed"):
        c.dispatch(ACTION, reserve=fail)
    with pytest.raises(ExchangeError):
        exchange.read("dispatch-permit.json", max_bytes=8192)
    assert process.closed


def test_stalled_reviewer_late_decision_has_no_dispatch_authority(native):
    c, exchange, process, _ = native; c.reviewer = lambda record: (time.sleep(0.2), decision(record))[1]
    c.launch = replace(c.launch, review_seconds=0.05)
    bind(c)
    result = c.dispatch(ACTION, reserve=lambda _: pytest.fail("late reservation"))
    assert result["disposition"] == "unknown_delivery" and process.closed
    time.sleep(0.15)
    with pytest.raises(ExchangeError):
        exchange.read("dispatch-permit.json", max_bytes=8192)


def test_out_of_scope_and_changed_exact_output_are_refused(native):
    c, exchange, process, _ = native; bind(c)
    with pytest.raises(NativeError):
        c.dispatch({**ACTION, "room": "other"}, reserve=lambda _: pytest.fail("reserved"))
    with pytest.raises(ExchangeError):
        exchange.read("proposal.json", max_bytes=8192)
    assert process.closed


def test_config_drift_and_ambient_environment_are_rejected(native):
    c, _, process, calls = native
    c.launch.fixture_config.write_bytes(b"changed")
    with pytest.raises(NativeError):
        c.prestart()
    assert not calls and not process.resumed


def test_environment_does_not_inherit_provider_credentials(native):
    c, _, _, calls = native
    c.launch = replace(c.launch, env={"OPENAI_API_KEY": "do-not-copy"})
    with pytest.raises(NativeError):
        c.prestart()
    assert not calls


def test_decision_digest_mismatch_prevents_reservation(native):
    c, _, process, _ = native
    c.reviewer = lambda record: {**decision(record), "review_sha256": "0" * 64}
    bind(c)
    with pytest.raises(NativeRecordingError):
        c.dispatch(ACTION, reserve=lambda _: pytest.fail("reserved mismatch"))
    assert c.failed and process.closed


def test_decision_write_failure_stops_before_reservation(native, monkeypatch):
    c, exchange, process, _ = native
    bind(c); put = exchange.put
    def fail(name, data, **kwargs):
        if name == "decision.json":
            raise OSError("private error")
        return put(name, data, **kwargs)
    monkeypatch.setattr(exchange, "put", fail)
    with pytest.raises(NativeRecordingError):
        c.dispatch(ACTION, reserve=lambda _: pytest.fail("reserved before durable decision"))
    assert c.failed and process.closed


def test_pathext_is_forwarded_as_explicit_windows_runtime_input(native):
    c, _, _, calls = native
    c.launch = replace(c.launch, env={"PATHEXT": ".COM;.EXE;.BAT;.CMD"})
    c.prestart()
    assert calls[0][1]["env"]["PATHEXT"] == ".COM;.EXE;.BAT;.CMD"


def test_startup_exit_preserves_decoded_process_diagnostics(native):
    c, store, process, _ = native; process.ready = None; process.fault = "exit"
    with pytest.raises(NativeError):
        c.prestart()
    receipt = json.loads(store.read("native-process.json", max_bytes=8192))
    assert receipt["capture_kind"] == "decoded_process_outcome_not_raw_bytes"
    assert receipt["observed_during"] == "terminal_wait" and receipt["returncode"] == 1
    assert store.read("native-stderr.txt", max_bytes=1048576) == b"fake native startup failure"


def test_program_files_runtime_variables_are_forwarded_explicitly(native):
    c, _, _, calls = native
    values = {"PROGRAMFILES": r"C:\Program Files", "PROGRAMFILES(X86)": r"C:\Program Files (x86)"}
    c.launch = replace(c.launch, env=values)
    c.prestart()
    assert all(calls[0][1]["env"][key] == value for key, value in values.items())
