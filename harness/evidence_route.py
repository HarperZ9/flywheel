"""Strict, filesystem-scoped transport for the evidence journey APIs."""
from __future__ import annotations

from pathlib import Path
from .evidence_journey import new_journey, project_journey, run_journey_check
from .evidence_packet import pack_journey_packet, verify_journey_packet
from .evidence_public import (
    TransportError, admitted_root as _root, error_response as _error,
    exact_request, json_ref as _json_ref, parse_json as _parse,
    public_result as _public_result, public_text as _text,
    relative_ref as _relative, within_root as _within,
)

ROUTE_PREFIX = "/api/evidence/"
_ACTIONS = frozenset(("start", "project", "check", "export", "recheck"))
_FIELDS = {
    "start": frozenset(("journey_id", "goal", "created_at", "intake_ref")),
    "project": frozenset(("journey_ref", "lens")),
    "check": frozenset(("journey_ref", "claim_id", "oracle_id",
                         "candidate_ref", "context_ref")),
    "export": frozenset(("journey_ref", "packet_ref")),
    "recheck": frozenset(("packet_ref", "expected_manifest_sha256")),
}
def _request(action: str, value: dict) -> dict:
    return exact_request(value, _FIELDS[action],
                         optional=("expected_manifest_sha256",)
                         if action == "recheck" else ())


def _start(req: dict, root: Path) -> tuple[dict, int]:
    intake = _json_ref(root, req["intake_ref"])
    journey_id = _text(req, "journey_id")
    goal = _text(req, "goal")
    created_at = _text(req, "created_at")
    try:
        return new_journey(journey_id=journey_id, goal=goal, intake=intake,
            created_at=created_at), 200
    except (TypeError, ValueError, RecursionError) as exc:
        raise TransportError("INVALID_METADATA", "journey metadata is invalid", 422) from exc


def _project(req: dict, root: Path) -> tuple[dict, int]:
    lens = _text(req, "lens")
    if lens.lower() not in {"rescue", "diagnose", "verify"}:
        raise TransportError("UNSUPPORTED_LENS", "lens must be Rescue, Diagnose, or Verify", 422)
    journey = _json_ref(root, req["journey_ref"])
    try:
        return project_journey(journey, lens=lens), 200
    except (TypeError, ValueError, RecursionError) as exc:
        raise TransportError("INVALID_JOURNEY", "journey cannot be projected", 422) from exc


def _check(req: dict, root: Path) -> tuple[dict, int]:
    journey = _json_ref(root, req["journey_ref"])
    context = _json_ref(root, req["context_ref"])
    candidate_ref = _relative(req["candidate_ref"]).as_posix()
    if context.get("candidate_ref") != candidate_ref:
        raise TransportError("INVALID_METADATA", "candidate references do not match", 422)
    result = run_journey_check(journey, _text(req, "claim_id"),
        _text(req, "oracle_id"), root / _relative(candidate_ref), context,
        artifact_root=root)
    return result, 422 if result.get("verdict") in {"UNDECIDED", "UNVERIFIABLE"} else 200


def _export(req: dict, root: Path) -> tuple[dict, int]:
    journey = _json_ref(root, req["journey_ref"])
    packet = _within(root, req["packet_ref"], must_exist=False)
    try:
        return pack_journey_packet(packet, journey=journey, artifact_root=root), 200
    except (OSError, TypeError, ValueError, RecursionError) as exc:
        raise TransportError("EXPORT_REFUSED", "journey packet could not be exported", 422) from exc


def _recheck(req: dict, root: Path) -> tuple[dict, int]:
    packet = _within(root, req["packet_ref"], must_exist=True)
    if not packet.is_dir():
        raise TransportError("INVALID_REF", "packet reference must name a directory")
    anchor = req.get("expected_manifest_sha256")
    result = verify_journey_packet(packet, expected_manifest_sha256=anchor)
    return result, 200 if result.get("verdict") in {"MATCH", "DRIFT"} else 422


_HANDLERS = {"start": _start, "project": _project, "check": _check,
             "export": _export, "recheck": _recheck}


def evidence_post(path: str, raw: bytes | str, *, root: Path) -> tuple[dict, int]:
    """Handle one evidence POST without provider, model, endpoint, or network calls."""
    try:
        if type(path) is not str or not path.startswith(ROUTE_PREFIX):
            raise TransportError("NOT_FOUND", "evidence route not found", 404)
        action = path[len(ROUTE_PREFIX):]
        if action not in _ACTIONS or "/" in action:
            raise TransportError("NOT_FOUND", "evidence route not found", 404)
        request = _request(action, _parse(raw))
        result, status = _HANDLERS[action](request, _root(root))
        return _public_result(action, result), status
    except TransportError as exc:
        return _error(exc)
    except Exception:
        return _error(TransportError(
            "INTERNAL_ERROR", "evidence transport failed without exposing host details", 500))
