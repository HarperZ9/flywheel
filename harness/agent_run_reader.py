"""Private, bounded reads of the existing content-addressed agent-run store."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
from urllib.parse import parse_qsl

from .evidence_json import strict_load_json
from .evidence_public import TransportError, error_response
from .private_artifact_fs import PrivateArtifactError, open_artifact_root

MAX_RUN_BYTES = 1_048_576
MAX_LIST_LIMIT = 500  # existing trace-benchmark helper contract
MAX_HTTP_LIMIT = 100
MAX_SCAN_ENTRIES = 1000
SCHEMA = "flywheel.agent-runs/v1"
_ID = re.compile(r"[0-9a-fA-F]{16}", re.ASCII)
_STATUS = {"INVALID_REQUEST": 400, "NOT_FOUND": 404, "TOO_LARGE": 413,
           "UNREADABLE": 422, "UNSAFE_PATH": 403, "UNAVAILABLE": 503}


def _fail(code: str) -> TransportError:
    return TransportError(code, {
        "INVALID_REQUEST": "agent run request is invalid",
        "NOT_FOUND": "agent run was not found",
        "TOO_LARGE": "agent run exceeds the read limit",
        "UNREADABLE": "agent run is not a readable JSON object",
        "UNSAFE_PATH": "agent run storage is not safely readable",
        "UNAVAILABLE": "agent run storage is unavailable",
    }[code], _STATUS[code])


def _id(value: object) -> str:
    if type(value) is not str or _ID.fullmatch(value) is None:
        raise _fail("INVALID_REQUEST")
    return value.lower()


def _storage_error(exc: Exception) -> TransportError:
    code = getattr(exc, "code", "")
    if code in {"NOT_FOUND", "TOO_LARGE", "UNSAFE_PATH"}:
        return _fail(code)
    if code == "NOT_REGULAR":
        return _fail("UNSAFE_PATH")
    if isinstance(exc, FileNotFoundError):
        return _fail("NOT_FOUND")
    return _fail("UNAVAILABLE")


def _read(fs, rid: str) -> dict:
    raw = fs.read_bytes(rid + ".json", max_bytes=MAX_RUN_BYTES)
    try:
        doc = strict_load_json(raw, max_bytes=MAX_RUN_BYTES, max_depth=32)
        if type(doc) is not dict:
            raise ValueError
        from .eval_store import _canonical
        canonical = _canonical(doc)
        doc["intact"] = hashlib.sha256(canonical.encode()).hexdigest()[:16] == rid
        return doc
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise _fail("UNREADABLE") from None


def _detail_response(run_root, run_id: str) -> tuple[dict, int]:
    try:
        rid = _id(run_id)  # before opening any filesystem object
        with open_artifact_root(Path(run_root) / "agent_runs", writable=False) as fs:
            return _read(fs, rid), 200
    except TransportError as exc:
        return error_response(exc)
    except (PrivateArtifactError, OSError) as exc:
        return error_response(_storage_error(exc))


def agent_run_detail(run_root, run_id: str) -> dict:
    return _detail_response(run_root, run_id)[0]


def _summary(rid: str, doc: dict) -> dict:
    intact = doc["intact"]
    row = {"run_id": rid, "intact": intact,
           "status": "TAMPERED" if not intact else str(doc.get("status", "DONE"))[:40]}
    for key in ("goal_excerpt", "endpoint", "steps", "verified", "duration_s", "ttva_s", "started"):
        value = doc.get(key)
        row[key] = value[:200] if type(value) is str else (
            value if value is None or type(value) in (bool, int, float) else None)
    return row


def _list_response(run_root, limit: int = 20) -> tuple[dict, int]:
    try:
        if type(limit) is not int or not 1 <= limit <= MAX_LIST_LIMIT:
            raise _fail("INVALID_REQUEST")
        directory = Path(run_root) / "agent_runs"
        with open_artifact_root(directory, writable=False) as fs:
            # POSIX enumeration uses the pinned descriptor. Windows holds all
            # ancestor handles against rename while this read capability lives.
            candidates, limited = [], False
            with fs.borrow_descriptor() as descriptor, os.scandir(
                descriptor.fd if descriptor.fd is not None else directory
            ) as entries:
                for index, entry in enumerate(entries):
                    if index == MAX_SCAN_ENTRIES:
                        limited = True
                        break
                    if not re.fullmatch(r"[0-9a-f]{16}\.json", entry.name):
                        continue
                    try:
                        stamp = entry.stat(follow_symlinks=False).st_mtime_ns
                    except OSError:
                        continue
                    candidates.append((stamp, entry.name[:-5]))
            rows = []
            for _, rid in sorted(candidates, reverse=True)[:limit]:
                try:
                    rows.append(_summary(rid, _read(fs, rid)))
                except (TransportError, PrivateArtifactError, OSError):
                    rows.append({"run_id": rid, "status": "UNREADABLE", "intact": False})
            result = {"schema": SCHEMA, "runs": rows, "total": len(rows)}
            if limited:
                result["scan_limited"] = True
            return result, 200
    except TransportError as exc:
        return error_response(exc)
    except (PrivateArtifactError, OSError) as exc:
        error = _storage_error(exc)
        if error.code == "NOT_FOUND":
            return {"schema": SCHEMA, "runs": [], "total": 0}, 200
        return error_response(error)


def agent_runs(run_root, limit: int = 20) -> dict:
    return _list_response(run_root, limit)[0]


def route_agent_history(path: str, query: str, run_root) -> tuple[dict, int]:
    try:
        if len(query) > 256:
            raise _fail("INVALID_REQUEST")
        try:
            pairs = parse_qsl(query, keep_blank_values=True, strict_parsing=True,
                              encoding="utf-8", errors="strict", max_num_fields=2)
        except (ValueError, UnicodeError):
            raise _fail("INVALID_REQUEST") from None
        if path == "/api/agent/run":
            if len(pairs) != 1 or pairs[0][0] != "id":
                raise _fail("INVALID_REQUEST")
            return _detail_response(run_root, _id(pairs[0][1]))
        else:
            if pairs and (len(pairs) != 1 or pairs[0][0] != "limit"
                          or re.fullmatch(r"[0-9]{1,3}", pairs[0][1]) is None):
                raise _fail("INVALID_REQUEST")
            limit = int(pairs[0][1]) if pairs else 20
            if not 1 <= limit <= MAX_HTTP_LIMIT:
                raise _fail("INVALID_REQUEST")
            return _list_response(run_root, limit)
    except TransportError as exc:
        return error_response(exc)
