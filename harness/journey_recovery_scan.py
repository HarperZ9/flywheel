"""Journey recovery scan helpers that preserve partial-read state."""
from __future__ import annotations

from pathlib import Path

from .evidence_json import canonical_bytes, canonical_sha256, strict_load_json
from .journey_migration import _atomic_replace
from .journey_projection import reduce_events
from .journey_store import HEAD_SCHEMA, REQUEST_SCHEMA, JourneyStore, JourneyStoreError
from .journey_types import validate_event
from .recovery_limited import safe_dirs, safe_exists, safe_files, state_ref

INDEX_SCHEMA = "flywheel.evidence-journey-index/v2"


def _all_events(root: Path, journey_dir: Path) -> tuple[list[tuple[dict, Path]], list[Path], list[str]]:
    valid, invalid, limited = [], [], []
    paths, boundary = safe_files(root, journey_dir / "events", "*.json")
    if boundary is not None:
        return [], [], [boundary]
    for path in paths:
        try:
            event = validate_event(strict_load_json(path.read_bytes()))
        except OSError:
            limited.append(state_ref(root, path)); continue
        except (TypeError, ValueError):
            invalid.append(path); continue
        expected = f"{event['sequence']:020d}-{event['event_sha256']}.json"
        if path.name != expected:
            invalid.append(path); continue
        valid.append((event, path))
    return valid, invalid, limited


def _matching_request(root: Path, journey_dir: Path, event: dict,
                      projection_sha: str) -> tuple[bool | None, list[str]]:
    matches, limited = 0, []
    paths, boundary = safe_files(root, journey_dir / "requests", "*.json")
    if boundary is not None:
        return None, [boundary]
    for path in paths:
        try:
            value = strict_load_json(path.read_bytes())
        except OSError:
            limited.append(state_ref(root, path)); continue
        except (TypeError, ValueError):
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
    return (None, limited) if limited else (matches == 1, [])


def _complete_candidate(root: Path, journey_dir: Path, head: dict, chain: list[dict],
                        candidates: list[tuple[dict, Path]]) -> tuple[int, list[tuple[dict, Path]], list[str]]:
    if len(candidates) != 1:
        return 0, candidates, []
    event, path = candidates[0]
    expected_name = f"{event['sequence']:020d}-{event['event_sha256']}.json"
    if (path.name != expected_name
            or event["prior_event_sha256"] != head["event_head_sha256"]
            or event["sequence"] != head["sequence"] + 1):
        return 0, candidates, []
    try:
        projection = reduce_events([*chain, event])
    except (TypeError, ValueError):
        return 0, candidates, []
    projection_sha = canonical_sha256(projection)
    matched, limited = _matching_request(root, journey_dir, event, projection_sha)
    if limited or not matched:
        return 0, candidates, limited
    next_head = {"schema": HEAD_SCHEMA, "journey_ref": journey_dir.name,
                 "sequence": event["sequence"],
                 "event_head_sha256": event["event_sha256"],
                 "projection_sha256": projection_sha}
    _atomic_replace(journey_dir / "projection.json", canonical_bytes(projection))
    _atomic_replace(journey_dir / "head.json", canonical_bytes(next_head))
    return 1, [], []


def _authoritative_index(root: Path) -> tuple[dict, list[str]]:
    owners, limited = {}, []
    owner_dirs, boundary = safe_dirs(root, root / "journeys" / "v2" / "owners")
    if boundary is not None:
        return {"schema": INDEX_SCHEMA, "owners": owners}, [boundary]
    store = JourneyStore(root)
    for owner_dir in owner_dirs:
        journeys = {}
        journey_dirs, boundary = safe_dirs(root, owner_dir)
        if boundary is not None:
            limited.append(boundary); continue
        for journey_dir in journey_dirs:
            try:
                head = store._read_head(journey_dir)
                if head is not None:
                    store._events_at_head(journey_dir, head)
                    journeys[journey_dir.name] = head["event_head_sha256"]
            except OSError:
                limited.append(state_ref(root, journey_dir))
            except (JourneyStoreError, TypeError, ValueError):
                continue
        if journeys:
            owners[owner_dir.name] = journeys
    return {"schema": INDEX_SCHEMA, "owners": owners}, limited


def _rebuild_index(root: Path) -> tuple[int, list[str]]:
    path = root / "journeys" / "v2" / "index.json"
    expected, limited = _authoritative_index(root)
    if limited:
        return 0, limited
    try:
        exists, boundary = safe_exists(root, path)
        if boundary is not None:
            return 0, [boundary]
        current = strict_load_json(path.read_bytes()) if exists else None
    except OSError:
        return 0, [state_ref(root, path)]
    except (TypeError, ValueError):
        current = None
    if current == expected:
        return 0, []
    try:
        _atomic_replace(path, canonical_bytes(expected))
    except OSError:
        return 0, [state_ref(root, path)]
    return 1, []
