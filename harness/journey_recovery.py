"""Fail-closed recovery for immutable Evidence Journey v2 stores."""
from __future__ import annotations

from pathlib import Path

from .evidence_json import canonical_bytes, canonical_sha256, strict_load_json
from .journey_migration import VERSION_SCHEMA, _atomic_replace
from .journey_projection import reduce_events
from .journey_store import (
    HEAD_SCHEMA, REQUEST_SCHEMA, JourneyStore, JourneyStoreError, MutationCommand,
)
from .journey_types import validate_event
from .operation_supervisor import (
    _valid_recovery_grammar, _valid_recovery_terminal,
)


INDEX_SCHEMA = "flywheel.evidence-journey-index/v2"
DIAGNOSTIC_SCHEMA = "flywheel.evidence-journey-recovery-diagnostic/v1"


def _result(*, completed=0, quarantined=0, indexes_rebuilt=0,
            starts_closed=False, read_only=False, diagnostic_refs=None) -> dict:
    return {"completed": completed, "quarantined": quarantined,
            "indexes_rebuilt": indexes_rebuilt, "starts_closed": starts_closed,
            "read_only": read_only, "diagnostic_refs": diagnostic_refs or []}


def _store_version(root: Path) -> tuple[int, bool]:
    path = root / "journeys" / "version.json"
    if not path.exists():
        return 2, False
    value = strict_load_json(path.read_bytes())
    if (set(value) != {"schema", "version"} or value.get("schema") != VERSION_SCHEMA
            or type(value.get("version")) is not int or value["version"] < 1):
        raise JourneyStoreError("STORE_COMMIT_FAILED")
    return value["version"], True


def _all_events(journey_dir: Path) -> tuple[list[tuple[dict, Path]], list[Path]]:
    valid, invalid = [], []
    for path in sorted((journey_dir / "events").glob("*.json")):
        try:
            event = validate_event(strict_load_json(path.read_bytes()))
        except (OSError, TypeError, ValueError):
            invalid.append(path)
            continue
        expected = f"{event['sequence']:020d}-{event['event_sha256']}.json"
        if path.name != expected:
            invalid.append(path)
            continue
        valid.append((event, path))
    return valid, invalid


def _matching_request(journey_dir: Path, event: dict, projection_sha: str) -> bool:
    matches = 0
    for path in sorted((journey_dir / "requests").glob("*.json")):
        try:
            value = strict_load_json(path.read_bytes())
        except (OSError, TypeError, ValueError):
            continue
        expected = {"schema", "client_request_sha256", "request_sha256", "sequence",
                    "event_head_sha256", "event_sha256", "projection_sha256"}
        if (set(value) == expected and value.get("schema") == REQUEST_SCHEMA
                and value.get("request_sha256") == event["request_sha256"]
                and value.get("sequence") == event["sequence"]
                and value.get("event_head_sha256") == event["event_sha256"]
                and value.get("event_sha256") == event["event_sha256"]
                and value.get("projection_sha256") == projection_sha
                and path.stem == value.get("client_request_sha256")):
            matches += 1
    return matches == 1


def _complete_candidate(journey_dir: Path, head: dict, chain: list[dict],
                        candidates: list[tuple[dict, Path]]) -> tuple[int, list[tuple[dict, Path]]]:
    if len(candidates) != 1:
        return 0, candidates
    event, path = candidates[0]
    expected_name = f"{event['sequence']:020d}-{event['event_sha256']}.json"
    if (path.name != expected_name
            or event["prior_event_sha256"] != head["event_head_sha256"]
            or event["sequence"] != head["sequence"] + 1):
        return 0, candidates
    try:
        projection = reduce_events([*chain, event])
    except (TypeError, ValueError):
        return 0, candidates
    projection_sha = canonical_sha256(projection)
    if not _matching_request(journey_dir, event, projection_sha):
        return 0, candidates
    next_head = {"schema": HEAD_SCHEMA, "journey_ref": journey_dir.name,
                 "sequence": event["sequence"],
                 "event_head_sha256": event["event_sha256"],
                 "projection_sha256": projection_sha}
    _atomic_replace(journey_dir / "projection.json", canonical_bytes(projection))
    _atomic_replace(journey_dir / "head.json", canonical_bytes(next_head))
    return 1, []


def _relative_refs(root: Path, events: list[tuple[dict, Path]], invalid: list[Path]) -> list[str]:
    paths = [path for _, path in events] + invalid
    return sorted({path.relative_to(root).as_posix() for path in paths})


def _diagnostic(root: Path, journey_dir: Path, refs: list[str], now: str) -> str:
    identity = canonical_sha256({"journey_ref": journey_dir.name, "event_refs": refs})[:24]
    relative = Path("journeys") / "recovery" / f"quarantine-{identity}.json"
    value = {"schema": DIAGNOSTIC_SCHEMA, "journey_ref": journey_dir.name,
             "reason": "AMBIGUOUS_OR_INVALID_ORPHAN", "observed_at": now,
             "event_refs": refs}
    _atomic_replace(root / relative, canonical_bytes(value))
    return relative.as_posix()


def _recover_journey(root: Path, journey_dir: Path, now: str) -> tuple[int, int, str | None]:
    store = JourneyStore(root)
    try:
        head = store._read_head(journey_dir)
        if head is None:
            return 0, 0, None
        chain = store._events_at_head(journey_dir, head)
    except (JourneyStoreError, OSError, TypeError, ValueError):
        refs = [path.relative_to(root).as_posix()
                for path in sorted((journey_dir / "events").glob("*.json"))]
        return 0, len(refs), _diagnostic(root, journey_dir, refs, now) if refs else None
    valid, invalid = _all_events(journey_dir)
    authoritative = {event["event_sha256"] for event in chain}
    candidates = [(event, path) for event, path in valid
                  if event["event_sha256"] not in authoritative]
    completed, remaining = _complete_candidate(journey_dir, head, chain, candidates)
    refs = _relative_refs(root, remaining, invalid)
    diagnostic = _diagnostic(root, journey_dir, refs, now) if refs else None
    return completed, len(refs), diagnostic


def _authoritative_index(root: Path) -> dict:
    owners = {}
    base = root / "journeys" / "v2" / "owners"
    if not base.exists():
        return {"schema": INDEX_SCHEMA, "owners": owners}
    store = JourneyStore(root)
    for owner_dir in sorted(path for path in base.iterdir() if path.is_dir()):
        journeys = {}
        for journey_dir in sorted(path for path in owner_dir.iterdir() if path.is_dir()):
            try:
                head = store._read_head(journey_dir)
                if head is not None:
                    store._events_at_head(journey_dir, head)
                    journeys[journey_dir.name] = head["event_head_sha256"]
            except (JourneyStoreError, OSError, TypeError, ValueError):
                continue
        if journeys:
            owners[owner_dir.name] = journeys
    return {"schema": INDEX_SCHEMA, "owners": owners}


def _rebuild_index(root: Path) -> int:
    path, expected = root / "journeys" / "v2" / "index.json", _authoritative_index(root)
    try:
        current = strict_load_json(path.read_bytes()) if path.exists() else None
    except (OSError, TypeError, ValueError):
        current = None
    if current == expected:
        return 0
    _atomic_replace(path, canonical_bytes(expected))
    return 1


_TERMINALS = frozenset(("check_completed", "check_failed", "check_cancelled"))
def _event_ref(root: Path, journey_dir: Path, event: dict) -> str:
    name = f"{event['sequence']:020d}-{event['event_sha256']}.json"
    return (journey_dir / "events" / name).relative_to(root).as_posix()


def _close_journey_starts(root: Path, owner_dir: Path, journey_dir: Path,
                          *, now: str) -> tuple[int, list[str]]:
    store, diagnostics, closed = JourneyStore(root), [], 0
    try:
        head = store._read_head(journey_dir)
        events = store._events_at_head(journey_dir, head) if head else []
    except (JourneyStoreError, OSError, TypeError, ValueError):
        return 0, []
    starts = [event for event in events if event["event_type"] == "check_started"]
    current_head, seen = (events[-1]["event_sha256"] if events else None), set()
    for start in starts:
        operation = start["payload"].get("operation_ref")
        identity = operation if type(operation) is str else start["event_sha256"]
        if identity in seen:
            continue
        seen.add(identity)
        related = [event for event in events
                   if event["payload"].get("operation_ref") == operation]
        duplicate = [event for event in related
                     if event["event_type"] == "check_started"]
        terminal = [event for event in related if event["event_type"] in _TERMINALS]
        authoritative = (start["actor_id"] == owner_dir.name
                         and start["journey_ref"] == journey_dir.name)
        grammar = _valid_recovery_grammar(events, start, terminal)
        if (authoritative and grammar and terminal
                and _valid_recovery_terminal(start, terminal)):
            continue
        if terminal or not authoritative or not grammar:
            refs = [_event_ref(root, journey_dir, event) for event in related or [start]]
            diagnostics.append(_diagnostic(root, journey_dir, refs, now))
            continue
        try:
            ack = store.append(MutationCommand(
                owner_ref=owner_dir.name, journey_ref=journey_dir.name,
                expected_event_head=current_head,
                client_request_id=f"recovery:{start['event_sha256']}",
                operation="check_failed", body={"occurred_at": now, "payload": {
                    "operation_ref": operation, "reason": "CHECK_INTERRUPTED",
                    "started_event_sha256": start["event_sha256"],
                }},
            ))
        except JourneyStoreError:
            refs = [_event_ref(root, journey_dir, start)]
            diagnostics.append(_diagnostic(root, journey_dir, refs, now))
            continue
        current_head = ack.event_head_sha256
        closed += 1
    return closed, diagnostics


def _close_abandoned_starts(store_root: Path, *, now: str) -> tuple[int, list[str]]:
    """Close only exact authoritative check starts; diagnose every ambiguity."""
    owners, closed, diagnostics = store_root / "journeys" / "v2" / "owners", 0, []
    if not owners.exists():
        return 0, []
    for owner_dir in sorted(path for path in owners.iterdir() if path.is_dir()):
        for journey_dir in sorted(path for path in owner_dir.iterdir() if path.is_dir()):
            count, refs = _close_journey_starts(
                store_root, owner_dir, journey_dir, now=now,
            )
            closed += count
            diagnostics.extend(refs)
    return closed, diagnostics


def recover_store(store_root: Path, *, now: str) -> dict:
    """Complete deterministic residue, quarantine ambiguity, and rebuild indexes."""
    root = Path(store_root)
    version, has_pointer = _store_version(root)
    if version > 2:
        refs = ["journeys/version.json"] if has_pointer else []
        return _result(read_only=True, diagnostic_refs=refs)
    completed, quarantined, diagnostics = 0, 0, []
    closed, start_refs = _close_abandoned_starts(root, now=now)
    diagnostics.extend(start_refs)
    owners = root / "journeys" / "v2" / "owners"
    if owners.exists():
        for owner_dir in sorted(path for path in owners.iterdir() if path.is_dir()):
            for journey_dir in sorted(path for path in owner_dir.iterdir() if path.is_dir()):
                done, held, ref = _recover_journey(root, journey_dir, now)
                completed += done
                quarantined += held
                if ref is not None:
                    diagnostics.append(ref)
    rebuilt = _rebuild_index(root)
    return _result(completed=completed, quarantined=quarantined,
                   indexes_rebuilt=rebuilt, starts_closed=bool(closed),
                   diagnostic_refs=diagnostics)
