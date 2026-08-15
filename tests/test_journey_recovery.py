import json
from pathlib import PurePosixPath

from harness.evidence_json import canonical_bytes, canonical_sha256
from harness.journey_recovery import recover_store
from harness.journey_projection import reduce_events
from harness.journey_store import JourneyStore, MutationCommand
from harness.journey_types import build_event


OWNER = "owner_recovery_aaaaaaaaaaaaaaaaaaaaaaaaaa"
JOURNEY = "jrn_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
NOW = "2026-08-14T20:00:00Z"
OPERATION = "op_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _genesis(root):
    return JourneyStore(root).create(MutationCommand(
        owner_ref=OWNER, journey_ref=JOURNEY, expected_event_head=None,
        client_request_id="genesis", operation="intake",
        body={"legacy_label": None, "goal": "Recover exact state", "intake": {},
              "occurred_at": "2026-08-14T19:00:00Z"},
    ))


def _journey_dir(root):
    return root / "journeys" / "v2" / "owners" / OWNER / JOURNEY


def _orphan(root, head, marker):
    request_key = canonical_sha256(f"orphan-{marker}")
    request_sha = canonical_sha256({"marker": marker})
    event = build_event(
        journey_ref=JOURNEY, sequence=1, event_type="record_next_action",
        occurred_at="2026-08-14T19:01:00Z", actor_id=OWNER,
        request_sha256=request_sha,
        payload={"next_actions": [{"marker": marker}]},
        prior_event_sha256=head,
    )
    path = _journey_dir(root) / "events" / f"{1:020d}-{event['event_sha256']}.json"
    path.write_bytes(canonical_bytes(event))
    genesis_path = next((_journey_dir(root) / "events").glob("00000000000000000000-*.json"))
    projection_sha = canonical_sha256(reduce_events([
        json.loads(genesis_path.read_bytes()), event,
    ]))
    request = {
        "schema": "flywheel.evidence-journey-request/v2",
        "client_request_sha256": request_key, "request_sha256": request_sha,
        "sequence": 1, "event_head_sha256": event["event_sha256"],
        "event_sha256": event["event_sha256"], "projection_sha256": projection_sha,
    }
    (_journey_dir(root) / "requests" / f"{request_key}.json").write_bytes(
        canonical_bytes(request),
    )
    return event, path


def _write_version(root, version):
    path = root / "journeys" / "version.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes({
        "schema": "flywheel.evidence-journey-store-version/v1", "version": version,
    }))
    return path


def _append(root, head, request_id, operation, payload):
    return JourneyStore(root).append(MutationCommand(
        owner_ref=OWNER, journey_ref=JOURNEY, expected_event_head=head,
        client_request_id=request_id, operation=operation,
        body={"occurred_at": "2026-08-14T19:02:00Z", "payload": payload},
    ))


def _started(root, head, *, duplicate=False):
    requested = _append(root, head, "check-request", "check_requested", {
        "operation_ref": OPERATION, "claim_id": "claim-root", "oracle_id": "ml",
    })
    payload = {
        "operation_ref": OPERATION, "claim_id": "claim-root", "oracle_id": "ml",
        "request_event_sha256": requested.event_sha256,
    }
    started = _append(
        root, requested.event_head_sha256, "check-start", "check_started", payload,
    )
    if not duplicate:
        return started
    return _append(
        root, started.event_head_sha256, "check-start-duplicate",
        "check_started", payload,
    )


def test_recovery_completes_only_one_deterministic_orphan_and_rebuilds_index(tmp_path):
    """Ignoring one valid successor would lose a complete durable mutation."""
    genesis = _genesis(tmp_path)
    event, path = _orphan(tmp_path, genesis.event_head_sha256, "complete")
    source_bytes = path.read_bytes()

    result = recover_store(tmp_path, now=NOW)

    projection = JourneyStore(tmp_path).load(OWNER, JOURNEY)
    index = json.loads((tmp_path / "journeys" / "v2" / "index.json").read_bytes())
    assert set(result) == {"completed", "quarantined", "indexes_rebuilt",
                           "starts_closed", "read_only", "diagnostic_refs"}
    assert result["completed"] == 1 and result["quarantined"] == 0
    assert result["indexes_rebuilt"] == 1 and result["starts_closed"] is False
    assert projection["event_head_sha256"] == event["event_sha256"]
    assert index["owners"][OWNER][JOURNEY] == event["event_sha256"]
    assert path.read_bytes() == source_bytes


def test_recovery_quarantines_ambiguous_successors_and_preserves_authoritative_head(tmp_path):
    """Choosing between two valid successors would invent an authoritative branch."""
    genesis = _genesis(tmp_path)
    first, first_path = _orphan(tmp_path, genesis.event_head_sha256, "first")
    second, second_path = _orphan(tmp_path, genesis.event_head_sha256, "second")
    before = {first_path: first_path.read_bytes(), second_path: second_path.read_bytes()}

    result = recover_store(tmp_path, now=NOW)

    projection = JourneyStore(tmp_path).load(OWNER, JOURNEY)
    assert result["completed"] == 0 and result["quarantined"] == 2
    assert result["starts_closed"] is False and result["read_only"] is False
    assert projection["event_head_sha256"] == genesis.event_head_sha256
    assert all(path.read_bytes() == raw for path, raw in before.items())
    assert result["diagnostic_refs"]
    assert all(not PurePosixPath(ref).is_absolute() and ".." not in PurePosixPath(ref).parts
               and "\\" not in ref for ref in result["diagnostic_refs"])
    diagnostic = json.loads((tmp_path / result["diagnostic_refs"][0]).read_bytes())
    assert set(diagnostic["event_refs"]) == {
        first_path.relative_to(tmp_path).as_posix(), second_path.relative_to(tmp_path).as_posix(),
    }
    assert first["prior_event_sha256"] == second["prior_event_sha256"]


def test_recovery_rebuilds_stale_index_from_authoritative_heads(tmp_path):
    """Copying stale index entries would expose a head not backed by immutable events."""
    genesis = _genesis(tmp_path)
    index_path = tmp_path / "journeys" / "v2" / "index.json"
    index_path.write_bytes(canonical_bytes({"schema": "bad", "owners": {}}))

    result = recover_store(tmp_path, now=NOW)

    index = json.loads(index_path.read_bytes())
    assert result["indexes_rebuilt"] == 1
    assert index["owners"] == {OWNER: {JOURNEY: genesis.event_head_sha256}}


def test_noncanonical_orphan_filename_is_quarantined_without_head_advance(tmp_path):
    """Trusting valid content under any filename would bypass the event layout."""
    genesis = _genesis(tmp_path)
    _, canonical = _orphan(tmp_path, genesis.event_head_sha256, "wrong-name")
    noncanonical = canonical.with_name("orphan.json")
    canonical.rename(noncanonical)

    result = recover_store(tmp_path, now=NOW)

    assert result["completed"] == 0 and result["quarantined"] == 1
    assert JourneyStore(tmp_path).load(OWNER, JOURNEY)["event_head_sha256"] == (
        genesis.event_head_sha256
    )
    diagnostic = json.loads((tmp_path / result["diagnostic_refs"][0]).read_bytes())
    assert diagnostic["event_refs"] == [noncanonical.relative_to(tmp_path).as_posix()]


def test_absent_start_layout_never_reports_a_closed_start(tmp_path):
    """Counting unrelated recovery work as start closure would invent an operation."""
    assert recover_store(tmp_path, now=NOW)["starts_closed"] is False


def test_unadmitted_ambiguous_start_like_files_are_left_unchanged(tmp_path):
    """Guessing a future start schema would mutate P1-T5 state without authority."""
    starts = tmp_path / "journeys" / "v2" / "operation-starts"
    starts.mkdir(parents=True)
    paths = [starts / "one.json", starts / "two.json"]
    for path in paths:
        path.write_bytes(canonical_bytes({"state": "started"}))
    before = [path.read_bytes() for path in paths]

    result = recover_store(tmp_path, now=NOW)

    assert result["starts_closed"] is False
    assert [path.read_bytes() for path in paths] == before


def test_recovery_closes_one_authoritative_abandoned_check_start(tmp_path):
    """Leaving an admitted start open after restart would invent a running process."""
    genesis = _genesis(tmp_path)
    started = _started(tmp_path, genesis.event_head_sha256)

    result = recover_store(tmp_path, now=NOW)

    journey_dir = _journey_dir(tmp_path)
    events = [json.loads(path.read_bytes())
              for path in sorted((journey_dir / "events").glob("*.json"))]
    terminals = [event for event in events if event["event_type"] in {
        "check_completed", "check_failed", "check_cancelled"}]
    assert result["starts_closed"] is True and len(terminals) == 1
    assert terminals[0]["event_type"] == "check_failed"
    assert terminals[0]["payload"] == {
        "operation_ref": OPERATION, "reason": "CHECK_INTERRUPTED",
        "started_event_sha256": started.event_sha256,
    }


def test_recovery_does_not_choose_between_duplicate_authoritative_starts(tmp_path):
    """Closing an ambiguous operation would manufacture a terminal owner decision."""
    genesis = _genesis(tmp_path)
    _started(tmp_path, genesis.event_head_sha256, duplicate=True)

    result = recover_store(tmp_path, now=NOW)

    events = [json.loads(path.read_bytes()) for path in sorted(
        (_journey_dir(tmp_path) / "events").glob("*.json"))]
    assert result["starts_closed"] is False and result["diagnostic_refs"]
    assert not any(event["event_type"] in {
        "check_completed", "check_failed", "check_cancelled"} for event in events)


def test_newer_schema_recovery_opens_read_only_without_rewriting_anything(tmp_path):
    """Running older recovery over a newer layout would make incompatible writes."""
    genesis = _genesis(tmp_path)
    pointer = _write_version(tmp_path, 3)
    before = {path.relative_to(tmp_path): path.read_bytes()
              for path in tmp_path.rglob("*") if path.is_file()}

    result = recover_store(tmp_path, now=NOW)

    after = {path.relative_to(tmp_path): path.read_bytes()
             for path in tmp_path.rglob("*") if path.is_file()}
    assert result == {
        "completed": 0, "quarantined": 0, "indexes_rebuilt": 0,
        "starts_closed": False, "read_only": True,
        "diagnostic_refs": ["journeys/version.json"],
    }
    assert after == before and pointer.read_bytes() == before[pointer.relative_to(tmp_path)]
    assert JourneyStore(tmp_path).load(OWNER, JOURNEY)["event_head_sha256"] == genesis.event_head_sha256
