"""Where the running gateway listens, written only after it has bound (7.1).

`<home>/gateway.endpoint` (schema `flywheel.gateway-endpoint/v1`) names the
literal loopback address, the port, the process id, the start time and the
proof version. Hooks connect only to what it names and never fall back to a
fixed port, so a squatter on 127.0.0.1:8799 while the gateway is down gets
nothing. The file is removed on clean shutdown; a stale one names a process
that is not running, which hooks check.

The gateway also writes a home pointer in the per-user local app-data folder
(capture_hooks.home.pointer_path), so a hook mounted without `--home` finds a
non-default FLYWHEEL_HOME. It does not take the pointer from another home whose
gateway is running: two engines with different homes for one user would
otherwise move the owner's capture to whichever started last. The engine logs
that it left the pointer, and `flywheel traces doctor` reports a pointer that
names another home.
"""
from __future__ import annotations

import atexit
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path

from .capture_hooks.client import ENDPOINT_SCHEMA, CaptureFailure, read_endpoint
from .capture_hooks.home import POINTER_SCHEMA, not_local, pointer_path, read_pointer
from .capture_hooks.protocol import LOOPBACK

FILENAME = "gateway.endpoint"
_log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _write_private(path: Path, doc: dict) -> None:
    from .operation_grants import _secure_owner_only
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(json.dumps(doc, sort_keys=True).encode("utf-8"))
    _secure_owner_only(temporary, directory=False)
    os.replace(temporary, path)


def write_endpoint(home, host: str, port: int, pid: int) -> Path:
    if host not in LOOPBACK:
        raise ValueError("REMOTE_NOT_SUPPORTED")
    path = Path(home) / FILENAME
    _write_private(path, {"schema": ENDPOINT_SCHEMA, "host": host, "port": int(port),
                          "pid": int(pid), "started_at": _now(), "proof_version": 1})
    return path


def remove_endpoint(home) -> None:
    path = Path(home) / FILENAME
    try:
        doc = json.loads(path.read_bytes())
        if doc.get("pid") == os.getpid():
            path.unlink()
    except FileNotFoundError:
        return
    except (OSError, ValueError, AttributeError) as exc:
        _log.warning("gateway endpoint file not removed (%s)", type(exc).__name__)


def write_pointer(home, target: Path | None = None) -> Path | None:
    target = target or pointer_path()
    if target is None:
        return None
    _write_private(target, {"schema": POINTER_SCHEMA,
                            "home": os.path.abspath(str(home)), "written_at": _now()})
    return target


def pointer_held_elsewhere(home, target: Path | None = None) -> Path | None:
    """The other home the pointer names while that home's gateway is running
    (its endpoint names a live process other than this one); else None."""
    other = read_pointer(target or pointer_path())
    if other is None or not_local(other):   # never open a network path to ask
        return None
    if os.path.normcase(os.path.abspath(str(other))) == \
            os.path.normcase(os.path.abspath(str(home))):
        return None
    try:
        doc = read_endpoint(other)
    except CaptureFailure:
        return None
    return None if doc.get("pid") == os.getpid() else other


def publish_endpoint(home, servers) -> Path | None:
    """After bind: name the first loopback listener, write the pointer, and
    remove the endpoint file at a clean exit. Nothing is published when only
    non-loopback interfaces are bound; hooks then report the gateway down."""
    for server in servers:
        host, port = server.server_address[:2]
        if host in LOOPBACK:
            path = write_endpoint(home, host, port, os.getpid())
            try:
                if pointer_held_elsewhere(home) is None:
                    write_pointer(home)
                else:
                    _log.warning("home pointer left in place: it names another home "
                                 "whose gateway is running; mount hooks with --home")
            except OSError as exc:  # hooks fall back to the profile default
                _log.warning("home pointer not written (%s)", type(exc).__name__)
            atexit.register(remove_endpoint, home)
            return path
    return None
