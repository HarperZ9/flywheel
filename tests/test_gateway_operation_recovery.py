import json

from harness.evidence_json import canonical_bytes, canonical_sha256
from harness.gateway_operation_recovery import recover_gateway_operations
from harness.journey_store import JourneyStore, MutationCommand


NOW = "2026-08-16T12:00:00Z"
OWNER = "owner_" + "a" * 32
JOURNEY = "jrn_" + "a" * 32
OPERATION = "op_" + "a" * 32


def _append(root, head, request, event_type, payload):
    return JourneyStore(root).append(MutationCommand(
        OWNER, JOURNEY, head, request, event_type,
        {"occurred_at": NOW, "payload": payload}))


def _queued(root, **changes):
    head = JourneyStore(root).create(MutationCommand(
        OWNER, JOURNEY, None, "genesis", "intake",
        {"legacy_label": None, "goal": "recover", "intake": {},
         "occurred_at": NOW})).event_head_sha256
    payload = {
        "operation_ref": OPERATION, "client_request_id": "agent-1",
        "action": "agent.run", "tool": "agent.run",
        "authorization_sha256": "a" * 64, "operation_sha256": "b" * 64,
        "arguments_sha256": "c" * 64, "grant_ref_sha256": "d" * 64,
        "execution_plan_sha256": "e" * 64,
    }
    payload.update(changes)
    return _append(root, head, "queue", "operation_queued", payload)


def _events(root):
    directory = root / "journeys" / "v2" / "owners" / OWNER / JOURNEY / "events"
    return [json.loads(path.read_bytes()) for path in sorted(directory.glob("*.json"))]


def test_recovery_closes_exact_queued_running_and_cancel_requested(tmp_path):
    for state in ("queued", "running", "cancel_requested"):
        root = tmp_path / state
        queued = _queued(root)
        head, basis = queued.event_head_sha256, queued.event_sha256
        if state != "queued":
            started = _append(root, head, "start", "operation_started", {
                "operation_ref": OPERATION,
                "queued_event_sha256": queued.event_sha256,
                "control_class": "windows_job_v1"})
            head, basis = started.event_head_sha256, started.event_sha256
        if state == "cancel_requested":
            cancel = _append(root, head, "cancel", "cancel_requested", {
                "operation_ref": OPERATION,
                "started_event_sha256": basis,
                "client_request_id": "stop-1",
                "authorization_sha256": "f" * 64, "timeout_ms": 5000})
            basis = cancel.event_sha256

        result = recover_gateway_operations(root, now=NOW)

        terminals = [event for event in _events(root)
                     if event["event_type"] == "operation_failed"]
        assert result["closed"] == 1 and result["ambiguous"] == 0
        assert len(terminals) == 1
        assert terminals[0]["payload"]["reason"] == "OPERATION_INTERRUPTED"
        assert terminals[0]["payload"]["basis_event_sha256"] == basis


def test_recovery_diagnoses_ambiguous_grammar_without_terminal(tmp_path):
    queued = _queued(tmp_path)
    _append(tmp_path, queued.event_head_sha256, "duplicate", "operation_queued",
            queued_payload := queued_event_payload(tmp_path))

    result = recover_gateway_operations(tmp_path, now=NOW)

    assert result["closed"] == 0 and result["ambiguous"] == 1
    assert result["diagnostic_refs"]
    assert not any(event["event_type"].startswith("operation_") and
                   event["event_type"] in {"operation_failed",
                                            "operation_completed",
                                            "operation_cancelled"}
                   for event in _events(tmp_path))


def test_recovery_diagnoses_invalid_operation_identity_without_closure(tmp_path):
    for name, changes in {
        "ref": {"operation_ref": "op_bad"},
        "action": {"action": "plugin.call"},
        "request": {"client_request_id": "../unsafe"},
    }.items():
        root = tmp_path / name
        _queued(root, **changes)

        result = recover_gateway_operations(root, now=NOW)

        assert result["closed"] == 0 and result["ambiguous"] == 1
        assert not any(event["event_type"] in {
            "operation_failed", "operation_completed", "operation_cancelled"}
            for event in _events(root))


def test_generic_recovery_ignores_phase_one_check_cancellation(tmp_path):
    head = JourneyStore(tmp_path).create(MutationCommand(
        OWNER, JOURNEY, None, "genesis", "intake",
        {"legacy_label": None, "goal": "check", "intake": {},
         "occurred_at": NOW})).event_head_sha256
    _append(tmp_path, head, "check-cancel", "cancel_requested", {
        "operation_ref": OPERATION, "started_event_sha256": "a" * 64,
        "timeout_s": 1.0})

    result = recover_gateway_operations(tmp_path, now=NOW)

    assert result == {"closed": 0, "ambiguous": 0,
                      "diagnostic_refs": []}
    assert not any(event["event_type"].startswith("operation_")
                   for event in _events(tmp_path))


def queued_event_payload(root):
    return next(event["payload"] for event in _events(root)
                if event["event_type"] == "operation_queued")


def test_recovery_leaves_existing_terminal_and_detects_result_tamper(tmp_path):
    queued = _queued(tmp_path)
    wrong = {
        "schema": "wrong", "operation_ref": OPERATION,
        "action": "agent.run", "state": "completed", "result": {"ok": True}}
    digest = canonical_sha256(wrong)
    result_dir = (tmp_path / "gateway-operations" / "v1" / "owners" /
                  OWNER / "results")
    result_dir.mkdir(parents=True)
    result_path = result_dir / f"{digest}.json"
    result_path.write_bytes(canonical_bytes(wrong))
    terminal = _append(tmp_path, queued.event_head_sha256, "terminal",
                       "operation_completed", {
        "operation_ref": OPERATION,
        "basis_event_sha256": queued.event_sha256,
        "result_sha256": digest})

    result = recover_gateway_operations(tmp_path, now=NOW)

    assert terminal.event_sha256 in {
        event["event_sha256"] for event in _events(tmp_path)}
    assert result["closed"] == 0 and result["ambiguous"] == 1
