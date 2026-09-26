"""The capture failure spool and suppression counter (7.1, I3, S14).

Each failed capture leaves one small JSON file under
`<home>/state/capture-failures/v1/`: schema, client, event, session id,
prompt key, reason code and time. It holds no prompt, no answer, no path and
no working directory; a session id is a random UUID and names no project, and
the session import route resolves the transcript from it later.

With FLYWHEEL_CAPTURE=off, every suppressed event appends a suppression
record, and the first one per session leaves a marker so the notice shows
once. The working directory in a suppression record is DPAPI-encrypted on
Windows and omitted elsewhere.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets

from . import protect

FAILURE_SCHEMA = "flywheel.capture-failure/v1"
SUPPRESSION_SCHEMA = "flywheel.capture-suppression/v1"
_SESSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_CODE = re.compile(r"[A-Z_]{3,40}(:[0-9]{3})?\Z")


def spool_dir(home: Path) -> Path:
    return Path(home) / "state" / "capture-failures" / "v1"


def clean_session(value) -> str | None:
    return value if type(value) is str and _SESSION.fullmatch(value) else None


def clean_key(value) -> str | None:
    return value if type(value) is str and _KEY.fullmatch(value) else None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + secrets.token_hex(4)


def _write_new(directory: Path, name: str, doc: dict) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(directory, 0o700)
    path = directory / name
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(json.dumps(doc, sort_keys=True).encode("utf-8"))
        stream.flush()
        os.fsync(stream.fileno())
    return path


def write_failure(home: Path, client: str, event: str, session_id, prompt_key,
                  code: str) -> bool:
    """One failure record; False when it could not be written."""
    doc = {"schema": FAILURE_SCHEMA, "client": client, "event": event,
           "session_id": clean_session(session_id), "prompt_key": clean_key(prompt_key),
           "reason_code": code if _CODE.fullmatch(code or "") else "UNKNOWN", "at": _now()}
    try:
        _write_new(spool_dir(home), f"f-{_stamp()}.json", doc)
        return True
    except OSError:
        return False


def _session_marker(session_id) -> str:
    raw = clean_session(session_id) or "unknown"
    return hashlib.sha256(("flywheel.capture.session.v1\0" + raw).encode()).hexdigest()[:32]


def note_suppression(home: Path, client: str, session_id, cwd: str) -> bool:
    """Count one suppressed event. True when it is the first of its session."""
    directory = spool_dir(home)
    doc = {"schema": SUPPRESSION_SCHEMA, "client": client, "at": _now(),
           "session_id": clean_session(session_id)}
    if protect.available():
        try:
            doc["cwd_protected"] = base64.b64encode(
                protect.protect(str(cwd).encode("utf-8"))).decode("ascii")
        except OSError:
            doc["cwd_protected"] = None
    _write_new(directory / "suppressed", f"s-{_stamp()}.json", doc)
    marker = directory / "suppressed" / f"session-{_session_marker(session_id)}.marker"
    try:
        _write_new(marker.parent, marker.name, {"schema": SUPPRESSION_SCHEMA})
        return True
    except FileExistsError:
        return False


def _records(directory: Path, pattern: str) -> list[dict]:
    out = []
    for path in sorted(directory.glob(pattern)) if directory.is_dir() else []:
        try:
            out.append(json.loads(path.read_bytes()))
        except (OSError, ValueError):
            out.append({"schema": "unreadable", "reason_code": "UNREADABLE_RECORD"})
    return out


def failures(home: Path) -> list[dict]:
    return _records(spool_dir(home), "f-*.json")


def suppressions(home: Path) -> list[dict]:
    return _records(spool_dir(home) / "suppressed", "s-*.json")


def suppression_count(home: Path) -> int:
    return len(suppressions(home))


def unacknowledged(home: Path) -> tuple[int, str | None]:
    """How many failures wait for `flywheel traces doctor --ack`, and since when."""
    records = failures(home)
    times = sorted(r.get("at") for r in records if type(r.get("at")) is str)
    return len(records), (times[0] if times else None)


def acknowledge(home: Path) -> int:
    """Move every failure record aside; they stay on disk, out of the count."""
    directory = spool_dir(home)
    moved = 0
    for path in sorted(directory.glob("f-*.json")) if directory.is_dir() else []:
        target = directory / "acknowledged"
        target.mkdir(exist_ok=True)
        os.replace(path, target / path.name)
        moved += 1
    return moved
