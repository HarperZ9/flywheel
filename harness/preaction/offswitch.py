"""offswitch.py -- turning the monitor off is a human-only, recorded act.

No tool argument can carry this authority (invariant: no tool argument carries
authority). The owner issues a one-use off grant through the grant store; a run
started with a consumed off grant runs unmonitored, and every call it makes is
recorded as coverage UNVERIFIABLE with the reason monitor-off-by-owner-grant,
so a reader never mistakes an unmonitored run for a clean one.
"""
from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..journey_lock import ExclusiveJourneyLock


class OffSwitchError(RuntimeError):
    """The off grant is missing, already used, expired, or not for this run."""


def _grants_path(home: Path) -> Path:
    return Path(home) / "off-grants.json"


def _read(home: Path) -> dict:
    p = _grants_path(home)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _write(home: Path, value: dict) -> None:
    Path(home).mkdir(parents=True, exist_ok=True)
    p = _grants_path(home)
    tmp = p.with_name(f".off.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(value, fh)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, p)


def issue_off_grant(home, *, run_id: str, clock, ttl_seconds: int = 300) -> str:
    """The owner issues one off grant for one run. Returns the grant ref."""
    now = datetime.fromisoformat(clock().replace("Z", "+00:00"))
    ref = "gnt_" + secrets.token_hex(16)
    with ExclusiveJourneyLock.acquire(Path(home) / ".off.lock", 5.0):
        grants = _read(Path(home))
        grants[ref] = {"run_id": run_id, "consumed": False,
                       "expires_at": (now + timedelta(seconds=ttl_seconds)).astimezone(
                           timezone.utc).isoformat().replace("+00:00", "Z")}
        _write(Path(home), grants)
    return ref


def monitor_off(home, *, grant_ref: str, run_id: str, clock, **monitor_kwargs):
    """Consume the off grant and return a Monitor that runs unmonitored for the
    run. Raises OffSwitchError if the grant is not a valid, unconsumed, matching
    one. The returned monitor still writes a record for every call."""
    from .core import Monitor
    with ExclusiveJourneyLock.acquire(Path(home) / ".off.lock", 5.0):
        grants = _read(Path(home))
        g = grants.get(grant_ref)
        if not g or g["consumed"] or g["run_id"] != run_id:
            raise OffSwitchError("off grant is missing, used, or not for this run")
        if clock() >= g["expires_at"]:
            raise OffSwitchError("off grant expired")
        g["consumed"] = True
        _write(Path(home), grants)
    return Monitor(home=home, clock=clock, unmonitored={"grant_ref": grant_ref, "run_id": run_id},
                   **monitor_kwargs)
