"""Fail-closed recovery for immutable Evidence Journey v2 stores."""
from __future__ import annotations

from pathlib import Path

from .evidence_json import canonical_bytes, canonical_sha256, strict_load_json
from .journey_migration import VERSION_SCHEMA, _atomic_replace
from .journey_recovery_scan import _all_events, _complete_candidate, _rebuild_index
from .recovery_limited import safe_dirs, safe_files, state_ref
from .journey_store import (
    JourneyStore, JourneyStoreError, MutationCommand,
)
from .operation_supervisor import (
    _valid_recovery_grammar, _valid_recovery_terminal,
)


DIAGNOSTIC_SCHEMA = "flywheel.evidence-journey-recovery-diagnostic/v1"


def _result(*, completed=0, quarantined=0, indexes_rebuilt=0,
            starts_closed=False, read_only=False, diagnostic_refs=None,
            recovery_limited=False, limited_refs=None) -> dict:
    result = {"completed": completed, "quarantined": quarantined,
              "indexes_rebuilt": indexes_rebuilt, "starts_closed": starts_closed,
              "read_only": read_only, "diagnostic_refs": diagnostic_refs or []}
    if recovery_limited or limited_refs:
        result["recovery_limited"] = True
        result["limited_refs"] = sorted(set(limited_refs or []))
    return result


def _store_version(root: Path) -> tuple[int, bool]:
    path = root / "journeys" / "version.json"
    if not path.exists():
        return 2, False
    value = strict_load_json(path.read_bytes())
    if (set(value) != {"schema", "version"} or value.get("schema") != VERSION_SCHEMA
            or type(value.get("version")) is not int or value["version"] < 1):
        raise JourneyStoreError("STORE_COMMIT_FAILED")
    return value["version"], True


def _relative_refs(root: Path, events: list[tuple[dict, Path]], invalid: list[Path]) -> list[str]:
    paths = [path for _, path in events] + invalid
    return sorted({path.relative_to(root).as_posix() for path in paths})


def _diagnostic(root: Path, journey_dir: Path, refs: list[str], now: str,
                reason: str = "AMBIGUOUS_OR_INVALID_ORPHAN") -> tuple[str | None, str | None]:
    identity = canonical_sha256({"journey_ref": journey_dir.name, "event_refs": refs,
                                 "reason": reason})[:24]
    relative = Path("journeys") / "recovery" / f"quarantine-{identity}.json"
    value = {"schema": DIAGNOSTIC_SCHEMA, "journey_ref": journey_dir.name,
             "reason": reason, "observed_at": now,
             "event_refs": refs}
    try:
        _atomic_replace(root / relative, canonical_bytes(value))
    except OSError:
        return None, relative.as_posix()
    return relative.as_posix(), None


def _record_diagnostic(root: Path, journey_dir: Path, refs: list[str],
                       now: str, reason: str) -> tuple[list[str], list[str]]:
    if not refs:
        return [], []
    ref, limited = _diagnostic(root, journey_dir, refs, now, reason)
    return ([ref] if ref else []), ([limited] if limited else [])


def _recover_journey(root: Path, journey_dir: Path, now: str) -> tuple[int, int, list[str], list[str]]:
    store = JourneyStore(root)
    try:
        head = store._read_head(journey_dir)
        if head is None:
            return 0, 0, [], []
        chain = store._events_at_head(journey_dir, head)
    except OSError:
        refs = [state_ref(root, journey_dir / "head.json")]
        diagnostics, limited = _record_diagnostic(
            root, journey_dir, refs, now, "UNREADABLE_JOURNEY")
        return 0, 1, diagnostics, refs + limited
    except (JourneyStoreError, TypeError, ValueError):
        paths, boundary = safe_files(root, journey_dir / "events", "*.json")
        if boundary is not None:
            diagnostics, limited = _record_diagnostic(
                root, journey_dir, [boundary], now, "UNREADABLE_EVENTS")
            return 0, 1, diagnostics, [boundary] + limited
        refs = [state_ref(root, path) for path in paths]
        diagnostics, limited = _record_diagnostic(
            root, journey_dir, refs, now, "AMBIGUOUS_OR_INVALID_ORPHAN")
        return 0, len(refs), diagnostics, limited
    valid, invalid, limited = _all_events(root, journey_dir)
    if limited:
        diagnostics, diag_limited = _record_diagnostic(
            root, journey_dir, limited, now, "UNREADABLE_EVENTS")
        return 0, len(limited), diagnostics, limited + diag_limited
    authoritative = {event["event_sha256"] for event in chain}
    candidates = [(event, path) for event, path in valid
                  if event["event_sha256"] not in authoritative]
    completed, remaining, limited = _complete_candidate(
        root, journey_dir, head, chain, candidates)
    if limited:
        diagnostics, diag_limited = _record_diagnostic(
            root, journey_dir, limited, now, "UNREADABLE_REQUESTS")
        return 0, len(limited), diagnostics, limited + diag_limited
    refs = _relative_refs(root, remaining, invalid)
    diagnostics, limited = _record_diagnostic(
        root, journey_dir, refs, now, "AMBIGUOUS_OR_INVALID_ORPHAN")
    return completed, len(refs), diagnostics, limited


_TERMINALS = frozenset(("check_completed", "check_failed", "check_cancelled"))
def _event_ref(root: Path, journey_dir: Path, event: dict) -> str:
    name = f"{event['sequence']:020d}-{event['event_sha256']}.json"
    return (journey_dir / "events" / name).relative_to(root).as_posix()


def _close_journey_starts(root: Path, owner_dir: Path, journey_dir: Path,
                          *, now: str) -> tuple[int, list[str], list[str]]:
    store, diagnostics, limited, closed = JourneyStore(root), [], [], 0
    try:
        head = store._read_head(journey_dir)
        events = store._events_at_head(journey_dir, head) if head else []
    except OSError:
        refs = [state_ref(root, journey_dir / "head.json")]
        diagnostics, limited = _record_diagnostic(
            root, journey_dir, refs, now, "UNREADABLE_JOURNEY")
        return 0, diagnostics, refs + limited
    except (JourneyStoreError, TypeError, ValueError):
        return 0, [], []
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
            refs, limited_refs = _record_diagnostic(
                root, journey_dir, refs, now, "AMBIGUOUS_OR_INVALID_ORPHAN")
            diagnostics.extend(refs); limited.extend(limited_refs)
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
            refs, limited_refs = _record_diagnostic(
                root, journey_dir, refs, now, "AMBIGUOUS_OR_INVALID_ORPHAN")
            diagnostics.extend(refs); limited.extend(limited_refs)
            continue
        current_head = ack.event_head_sha256
        closed += 1
    return closed, diagnostics, limited


def _close_abandoned_starts(store_root: Path, *, now: str) -> tuple[int, list[str], list[str]]:
    """Close only exact authoritative check starts; diagnose every ambiguity."""
    owners, closed, diagnostics, limited = (
        store_root / "journeys" / "v2" / "owners", 0, [], [])
    owner_dirs, boundary = safe_dirs(store_root, owners)
    if boundary is not None:
        return 0, [], [boundary]
    for owner_dir in owner_dirs:
        journey_dirs, boundary = safe_dirs(store_root, owner_dir)
        if boundary is not None:
            limited.append(boundary)
            continue
        for journey_dir in journey_dirs:
            count, refs, limited_refs = _close_journey_starts(
                store_root, owner_dir, journey_dir, now=now,
            )
            closed += count
            diagnostics.extend(refs)
            limited.extend(limited_refs)
    return closed, diagnostics, limited


def recover_store(store_root: Path, *, now: str) -> dict:
    """Complete deterministic residue, quarantine ambiguity, and rebuild indexes."""
    root = Path(store_root)
    limited_refs = []
    try:
        version, has_pointer = _store_version(root)
    except OSError:
        limited_refs.append(state_ref(root, root / "journeys" / "version.json"))
        return _result(read_only=True, recovery_limited=True,
                       limited_refs=limited_refs)
    if version > 2:
        refs = ["journeys/version.json"] if has_pointer else []
        return _result(read_only=True, diagnostic_refs=refs)
    completed, quarantined, diagnostics = 0, 0, []
    closed, start_refs, start_limited = _close_abandoned_starts(root, now=now)
    diagnostics.extend(start_refs)
    limited_refs.extend(start_limited)
    owners = root / "journeys" / "v2" / "owners"
    owner_dirs, boundary = safe_dirs(root, owners)
    if boundary is not None:
        limited_refs.append(boundary)
    for owner_dir in owner_dirs:
        journey_dirs, boundary = safe_dirs(root, owner_dir)
        if boundary is not None:
            limited_refs.append(boundary)
            continue
        for journey_dir in journey_dirs:
            done, held, refs, limited = _recover_journey(root, journey_dir, now)
            completed += done
            quarantined += held
            diagnostics.extend(refs)
            limited_refs.extend(limited)
    from .journey_export_tx import recover_export_transactions
    try:
        export_done, export_held, export_refs = recover_export_transactions(
            root, now=now)
    except OSError:
        export_done, export_held, export_refs = 0, 0, []
        limited_refs.append(state_ref(
            root, root / "journey-exports" / "v2" / "owners"))
    completed += export_done
    quarantined += export_held
    diagnostics.extend(export_refs)
    rebuilt = 0
    if not limited_refs:
        rebuilt, index_limited = _rebuild_index(root)
        limited_refs.extend(index_limited)
    return _result(completed=completed, quarantined=quarantined,
                   indexes_rebuilt=rebuilt, starts_closed=bool(closed),
                   diagnostic_refs=diagnostics,
                   recovery_limited=bool(limited_refs),
                   limited_refs=limited_refs)
