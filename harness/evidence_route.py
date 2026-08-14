"""Strict, filesystem-scoped transport for the evidence journey APIs."""
from __future__ import annotations

import os
from pathlib import Path
import re

from .bundle import BundleError, safe_relative, scan_for_secrets
from .evidence_json import canonical_bytes, strict_load_json
from .evidence_journey import new_journey, project_journey, run_journey_check
from .evidence_packet import pack_journey_packet, verify_journey_packet

ERROR_SCHEMA = "flywheel.evidence-transport-error/v1"
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
_SECRET_KEYS = frozenset(("api_key", "access_token", "refresh_token", "token",
    "password", "secret", "credential", "credentials", "private_key",
    "authorization", "cookie", "environment", "env"))
_WINDOWS_PATH = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]")
_UNC_PATH = re.compile(r"(?<!:)(?:\\\\|//)[^\\/\s]+[\\/][^\s]+")
_POSIX_PATH = re.compile(r"(?<![\w:/\\])/(?!/)[^\s]+")


class TransportError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def _error(exc: TransportError) -> tuple[dict, int]:
    return ({"schema": ERROR_SCHEMA,
             "error": {"code": exc.code, "message": exc.message}}, exc.status)


def _parse(raw: bytes | str) -> dict:
    try:
        value = strict_load_json(raw, max_bytes=1_048_576, max_depth=16)
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        if "top-level" in str(exc):
            raise TransportError("INVALID_REQUEST", "request body must be an object") from exc
        raise TransportError("INVALID_JSON", "request body is not strict JSON") from exc
    return value


def _request(action: str, value: dict) -> dict:
    expected = _FIELDS[action]
    extra, missing = value.keys() - expected, expected - value.keys()
    if action == "recheck":
        missing.discard("expected_manifest_sha256")
    if extra:
        raise TransportError("UNKNOWN_FIELD", "request contains unsupported fields")
    if missing:
        raise TransportError("MISSING_FIELD", "request is missing required fields")
    return value


def _public_metadata(value: object) -> None:
    if type(value) is dict:
        for key, item in value.items():
            _public_metadata(key)
            normalized = key.lower().replace("-", "_")
            if (normalized in _SECRET_KEYS or
                    normalized.endswith(("_api_key", "_private_key", "_password",
                                         "_secret", "_credential", "_token"))):
                raise TransportError("UNSAFE_METADATA", "metadata contains a secret-bearing field", 422)
            if key == "ref" or key.endswith(("_ref", "_refs")):
                refs = item if type(item) is list else [item]
                try:
                    for ref in refs:
                        safe_relative(ref)
                except (BundleError, TypeError, ValueError) as exc:
                    raise TransportError("UNSAFE_METADATA", "metadata contains an unsafe reference", 422) from exc
            _public_metadata(item)
    elif type(value) is list:
        for item in value:
            _public_metadata(item)
    elif type(value) is str:
        if scan_for_secrets(value):
            raise TransportError("UNSAFE_METADATA", "metadata contains secret-shaped content", 422)
        if (_WINDOWS_PATH.search(value) or _UNC_PATH.search(value) or
                _POSIX_PATH.search(value)):
            raise TransportError("UNSAFE_METADATA", "metadata contains a host path", 422)


def _public_result(action: str, value: dict) -> dict:
    try:
        if type(value) is not dict:
            raise TypeError("transport result must be an object")
        result = dict(value)
        if action == "check" and result.get("unverifiable_reason") and "reason" in result:
            result["reason"] = "registered oracle could not verify the submitted evidence"
        if action == "check" and result.get("unverifiable_reason") == "ORACLE_UNAVAILABLE":
            result.pop("oracle_id", None)
            result["does_not_prove"] = ["the requested claim was not checked"]
        if action in {"export", "recheck"} and "detail" in result:
            result["detail"] = "packet could not be verified from admitted evidence"
        result = strict_load_json(canonical_bytes(result),
                                  max_bytes=1_048_576, max_depth=32)
        _public_metadata(result)
    except (TransportError, TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise TransportError("UNSAFE_RESULT",
            "evidence transport produced unsafe metadata", 500) from exc
    return result


def _root(value: Path) -> Path:
    try:
        resolved = Path(value).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise TransportError("ROOT_UNAVAILABLE", "evidence root is unavailable", 500) from exc
    if not resolved.is_dir():
        raise TransportError("ROOT_UNAVAILABLE", "evidence root is unavailable", 500)
    return resolved


def _relative(ref: object) -> Path:
    try:
        rel = safe_relative(ref)
    except (BundleError, TypeError, ValueError) as exc:
        raise TransportError("INVALID_REF", "reference must be public-safe and relative") from exc
    return rel


def _within(root: Path, ref: object, *, must_exist: bool) -> Path:
    rel = _relative(ref)
    candidate = root / rel
    try:
        resolved = candidate.resolve(strict=must_exist)
        if os.path.commonpath((os.path.normcase(str(root)),
                               os.path.normcase(str(resolved)))) != os.path.normcase(str(root)):
            raise TransportError("INVALID_REF", "reference escapes the evidence root")
    except FileNotFoundError as exc:
        raise TransportError("MISSING_REF", "referenced artifact does not exist", 404) from exc
    except (OSError, RuntimeError, ValueError) as exc:
        raise TransportError("INVALID_REF", "reference cannot be admitted") from exc
    return root / rel


def _json_ref(root: Path, ref: object) -> dict:
    path = _within(root, ref, must_exist=True)
    if not path.is_file():
        raise TransportError("INVALID_REF", "referenced artifact must be a file")
    try:
        value = strict_load_json(path.read_bytes(), max_bytes=1_048_576, max_depth=32)
    except (OSError, TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise TransportError("INVALID_ARTIFACT", "referenced artifact is not strict JSON", 422) from exc
    if type(value) is not dict:
        raise TransportError("INVALID_ARTIFACT", "referenced JSON must be an object", 422)
    _public_metadata(value)
    return value


def _text(req: dict, name: str) -> str:
    value = req.get(name)
    if type(value) is not str or not value.strip():
        raise TransportError("INVALID_METADATA", f"{name} must be a non-empty string", 422)
    _public_metadata(value)
    return value


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
