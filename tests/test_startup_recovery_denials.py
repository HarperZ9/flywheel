import json
from pathlib import Path, PurePosixPath

from harness.evidence_json import canonical_bytes, canonical_sha256
import harness.gateway as gateway
import harness.journey_export_tx as journey_export_tx
import harness.journey_recovery as journey_recovery
import harness.journey_service as journey_service
from harness.desktop_status import desktop_status
from harness.gateway_operation_recovery import recover_gateway_operations
from harness.journey_projection import reduce_events
from harness.journey_store import JourneyStore, MutationCommand
from harness.journey_types import build_event


NOW = "2026-09-10T12:00:00Z"
OWNER = "owner_" + "d" * 32
JOURNEY = "jrn_" + "d" * 32
READABLE_JOURNEY = "jrn_" + "e" * 32
OPERATION = "op_" + "d" * 32


def _append(root, journey_ref, head, request, event_type, payload):
    return JourneyStore(root).append(MutationCommand(
        OWNER, journey_ref, head, request, event_type,
        {"occurred_at": NOW, "payload": payload}))


def _genesis(root, journey_ref=JOURNEY):
    return JourneyStore(root).create(MutationCommand(
        OWNER, journey_ref, None, "genesis", "intake",
        {"legacy_label": None, "goal": "recover denied state", "intake": {},
         "occurred_at": NOW}))


def _journey_dir(root, journey_ref=JOURNEY):
    return root / "journeys" / "v2" / "owners" / OWNER / journey_ref


def _orphan(root, journey_ref, head, marker):
    request_key = canonical_sha256(f"denied-orphan-{marker}")
    request_sha = canonical_sha256({"marker": marker})
    event = build_event(
        journey_ref=journey_ref, sequence=1, event_type="record_next_action",
        occurred_at=NOW, actor_id=OWNER, request_sha256=request_sha,
        payload={"next_actions": [{"marker": marker}]},
        prior_event_sha256=head)
    directory = _journey_dir(root, journey_ref)
    path = directory / "events" / f"{event['sequence']:020d}-{event['event_sha256']}.json"
    path.write_bytes(canonical_bytes(event))
    genesis_path = next((directory / "events").glob("00000000000000000000-*.json"))
    projection_sha = canonical_sha256(reduce_events([
        json.loads(genesis_path.read_bytes()), event]))
    request = {
        "schema": "flywheel.evidence-journey-request/v2",
        "client_request_sha256": request_key, "request_sha256": request_sha,
        "sequence": 1, "event_head_sha256": event["event_sha256"],
        "event_sha256": event["event_sha256"],
        "projection_sha256": projection_sha}
    (directory / "requests" / f"{request_key}.json").write_bytes(
        canonical_bytes(request))
    return event, path


def _deny_read_head(monkeypatch, denied):
    original = JourneyStore._read_head

    def guarded(self, journey_dir):
        if journey_dir == denied:
            raise PermissionError("denied private path")
        return original(self, journey_dir)

    monkeypatch.setattr(JourneyStore, "_read_head", guarded)


def _deny_glob(monkeypatch, denied_dir):
    original = Path.glob

    def guarded(self, pattern):
        if self == denied_dir:
            raise PermissionError("denied private path")
        return original(self, pattern)

    monkeypatch.setattr(Path, "glob", guarded)


def _diagnostic(root, ref):
    return json.loads((root / ref).read_bytes())


def _assert_safe_refs(refs):
    for ref in refs:
        path = PurePosixPath(ref)
        assert not path.is_absolute() and ".." not in path.parts
        assert "\\" not in ref and "denied private path" not in ref


def test_recover_store_reports_unreadable_journey_without_index_rebuild(
        tmp_path, monkeypatch):
    """Rebuilding the index after a denied journey scan would erase real state."""
    _genesis(tmp_path)
    denied = _journey_dir(tmp_path)
    index = tmp_path / "journeys" / "v2" / "index.json"
    before = canonical_bytes({"schema": "sentinel", "owners": {"kept": {}}})
    index.write_bytes(before)
    _deny_read_head(monkeypatch, denied)
    _deny_glob(monkeypatch, denied / "events")

    result = journey_recovery.recover_store(tmp_path, now=NOW)

    assert result["completed"] == 0 and result["indexes_rebuilt"] == 0
    assert result["recovery_limited"] is True
    assert index.read_bytes() == before
    assert result["diagnostic_refs"]
    _assert_safe_refs(result["diagnostic_refs"] + result["limited_refs"])
    diagnostic = _diagnostic(tmp_path, result["diagnostic_refs"][0])
    assert diagnostic["reason"] == "UNREADABLE_JOURNEY"
    assert diagnostic["event_refs"] == [
        denied.relative_to(tmp_path).as_posix() + "/head.json"]


def test_recover_store_does_not_complete_orphan_when_requests_are_unreadable(
        tmp_path, monkeypatch):
    """Completing an orphan without reading requests would guess idempotency."""
    genesis = _genesis(tmp_path)
    event, _ = _orphan(tmp_path, JOURNEY, genesis.event_head_sha256, "request")
    _deny_glob(monkeypatch, _journey_dir(tmp_path) / "requests")

    result = journey_recovery.recover_store(tmp_path, now=NOW)

    projection = JourneyStore(tmp_path).load(OWNER, JOURNEY)
    assert result["completed"] == 0 and result["recovery_limited"] is True
    assert projection["event_head_sha256"] == genesis.event_head_sha256
    assert projection["event_head_sha256"] != event["event_sha256"]


def test_recover_store_completes_readable_journey_but_preserves_index_when_scan_limited(
        tmp_path, monkeypatch):
    """A partial owner scan must not become an authoritative global index."""
    _genesis(tmp_path)
    denied = _journey_dir(tmp_path)
    readable = _genesis(tmp_path, READABLE_JOURNEY)
    event, _ = _orphan(tmp_path, READABLE_JOURNEY,
                       readable.event_head_sha256, "readable")
    index = tmp_path / "journeys" / "v2" / "index.json"
    before = canonical_bytes({"schema": "sentinel", "owners": {"kept": {}}})
    index.write_bytes(before)
    _deny_read_head(monkeypatch, denied)

    result = journey_recovery.recover_store(tmp_path, now=NOW)

    assert result["completed"] == 1 and result["indexes_rebuilt"] == 0
    assert result["recovery_limited"] is True
    assert index.read_bytes() == before
    projection = JourneyStore(tmp_path).load(OWNER, READABLE_JOURNEY)
    assert projection["event_head_sha256"] == event["event_sha256"]


def test_recover_store_survives_denied_diagnostic_write(
        tmp_path, monkeypatch):
    """Diagnostic write denial must not turn limited recovery into startup exit."""
    _genesis(tmp_path)
    denied = _journey_dir(tmp_path)
    _deny_read_head(monkeypatch, denied)
    original = journey_recovery._atomic_replace

    def guarded(path, data):
        if "recovery" in path.parts:
            raise PermissionError("denied private path")
        return original(path, data)

    monkeypatch.setattr(journey_recovery, "_atomic_replace", guarded)

    result = journey_recovery.recover_store(tmp_path, now=NOW)

    assert result["recovery_limited"] is True
    assert result["diagnostic_refs"] == []
    _assert_safe_refs(result["limited_refs"])


def test_gateway_operation_recovery_marks_unreadable_group_limited_without_terminal(
        tmp_path, monkeypatch):
    """Closing an unreadable operation would invent a terminal event."""
    queued = _append(tmp_path, JOURNEY, _genesis(tmp_path).event_head_sha256,
                     "queue", "operation_queued", {
                         "operation_ref": OPERATION,
                         "client_request_id": "agent-1",
                         "action": "agent.run", "tool": "agent.run",
                         "authorization_sha256": "a" * 64,
                         "operation_sha256": "b" * 64,
                         "arguments_sha256": "c" * 64,
                         "grant_ref_sha256": "d" * 64,
                         "execution_plan_sha256": "e" * 64})
    _deny_read_head(monkeypatch, _journey_dir(tmp_path))

    result = recover_gateway_operations(tmp_path, now=NOW)

    events = [json.loads(path.read_bytes())
              for path in sorted((_journey_dir(tmp_path) / "events").glob("*.json"))]
    assert result["closed"] == 0 and result["ambiguous"] == 1
    assert result["recovery_limited"] is True
    _assert_safe_refs(result["limited_refs"])
    assert not any(event["event_type"] == "operation_failed" for event in events)
    assert events[-1]["event_sha256"] == queued.event_sha256


def test_gateway_operation_recovery_marks_constructor_denial_limited(
        tmp_path, monkeypatch):
    """JourneyService hardening denial must not leak private text or close."""
    queued = _append(tmp_path, JOURNEY, _genesis(tmp_path).event_head_sha256,
                     "queue", "operation_queued", {
                         "operation_ref": OPERATION,
                         "client_request_id": "agent-1",
                         "action": "agent.run", "tool": "agent.run",
                         "authorization_sha256": "a" * 64,
                         "operation_sha256": "b" * 64,
                         "arguments_sha256": "c" * 64,
                         "grant_ref_sha256": "d" * 64,
                         "execution_plan_sha256": "e" * 64})
    owner_dir = _journey_dir(tmp_path).parent
    original = journey_service._secure_owner_only

    def guarded(path, *, directory):
        if Path(path) == owner_dir:
            raise PermissionError("denied private path X:/private-state/secret")
        return original(path, directory=directory)

    monkeypatch.setattr(journey_service, "_secure_owner_only", guarded)

    result = recover_gateway_operations(tmp_path, now=NOW)

    assert result["closed"] == 0 and result["ambiguous"] == 1
    assert result["recovery_limited"] is True
    assert result["limited_refs"] == [owner_dir.relative_to(tmp_path).as_posix()]
    assert "X:/private-state" not in json.dumps(result)
    events = [json.loads(path.read_bytes())
              for path in sorted((_journey_dir(tmp_path) / "events").glob("*.json"))]
    assert events[-1]["event_sha256"] == queued.event_sha256


def test_recover_store_marks_export_root_denial_limited_without_index_rebuild(
        tmp_path, monkeypatch):
    """Export transaction root denial is existing state, not startup failure."""
    _genesis(tmp_path)
    owners = tmp_path / "journey-exports" / "v2" / "owners"
    owners.mkdir(parents=True)
    original = journey_export_tx._prepare_private

    def guarded(path, state_root):
        if Path(path) == owners:
            raise PermissionError("denied private path X:/private-state/secret")
        return original(path, state_root)

    monkeypatch.setattr(journey_export_tx, "_prepare_private", guarded)

    result = journey_recovery.recover_store(tmp_path, now=NOW)

    assert result["completed"] == 0 and result["indexes_rebuilt"] == 0
    assert result["recovery_limited"] is True
    assert result["limited_refs"] == ["journey-exports/v2/owners"]
    assert "X:/private-state" not in json.dumps(result)
    assert not (tmp_path / "journeys" / "v2" / "index.json").exists()


def test_gateway_startup_reaches_status_with_limited_recovery(
        tmp_path, monkeypatch):
    """Startup must surface limited recovery instead of exiting before status."""
    fake_home = tmp_path / "home"
    state_root = fake_home / ".flywheel" / "state"
    _genesis(state_root)
    denied = _journey_dir(state_root)
    _deny_read_head(monkeypatch, denied)
    _deny_glob(monkeypatch, denied / "events")
    monkeypatch.delenv("FLYWHEEL_HOME", raising=False)
    monkeypatch.setattr(gateway.Path, "home", staticmethod(lambda: fake_home))
    monkeypatch.setattr(gateway, "_serve_all", lambda servers: None)

    exit_code = gateway.main(["--port", "0", "--root", str(tmp_path)])

    assert exit_code == 0
    assert gateway._Handler.startup_recovery["journeys"]["recovery_limited"]
    doc = desktop_status(
        {"n_lanes": 0, "by_status": {"live": 0}},
        startup_recovery=gateway._Handler.startup_recovery)
    assert doc["status"] == "degraded"
    assert doc["startup_recovery"]["limited"] is True
    assert doc["startup_recovery"]["journeys"]["limited_count"] >= 1
