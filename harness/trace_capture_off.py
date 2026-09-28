"""Capture-off events reach the custody ledger and the witness (7.1, I15).

With FLYWHEEL_CAPTURE=off the hook contacts no gateway and writes one
suppression record in the spool (the hook is standard-library only and does
not write the ledger). The gateway folds new records in when it answers a
hello, and the doctor does the same: one `capture_suppressed` ledger entry
per client and project with its count, and one witness event per entry. The
project is a keyed digest of the working directory (custody key), so the
ledger names no path; without the key it reads `unknown`. The names of the
records already folded in are kept beside them, so each is counted once.

A record from a lane process names its lane and no directory. Its project is
`lane:<lane>`, so every call a lane makes folds into one entry per fold, and
the record is removed once its count is in the ledger: the engine starts every
lane child with capture off, and those records would otherwise grow the spool
without bound and bury an owner's own opt-out.
"""
from __future__ import annotations

import base64
from collections import Counter
import hashlib
import hmac
import json
import logging
from pathlib import Path

_log = logging.getLogger(__name__)
DONE = ".ledgered"


def _project(record: dict, key: bytes | None) -> str:
    from .capture_hooks import protect, spool
    lane = record.get("lane")
    if type(lane) is str and spool._LANE.fullmatch(lane):
        return f"lane:{lane}"
    blob = record.get("cwd_protected")
    if not blob or key is None or not protect.available():
        return "unknown"
    try:
        cwd = protect.unprotect(base64.b64decode(blob))
    except (OSError, ValueError):
        return "unreadable"
    return hmac.new(key, b"project\x00" + cwd, hashlib.sha256).hexdigest()[:16]


def _key(home: Path, owner: str) -> bytes | None:
    from .trace_keystore import Keystore
    try:
        return Keystore(home / "state", owner).custody_key(create=False)
    except Exception as exc:  # no key store: the project reads unknown, logged
        _log.warning("custody key unavailable for suppression records (%s)",
                     type(exc).__name__)
        return None


def record_suppressions(home, owner: str, *, sink=None) -> int:
    """Fold new suppression records into the ledger; the number folded."""
    from .capture_hooks import spool
    from .trace_custody_ledger import CustodyLedger
    from .trace_custody_lock import custody_lock
    from .trace_witness import default_sink, event_text
    home = Path(home)
    folder = spool.spool_dir(home) / "suppressed"
    if not folder.is_dir():
        return 0
    with custody_lock(home / "state"):
        done_path = folder / DONE
        done = set(done_path.read_text(encoding="ascii").split()) if done_path.exists() else set()
        new = [p for p in sorted(folder.glob("s-*.json")) if p.name not in done]
        if not new:
            return 0
        key, groups, lane_records = _key(home, owner), Counter(), []
        for path in new:
            try:
                record = json.loads(path.read_bytes())
            except (OSError, ValueError):
                record = {}
            client = record.get("client") if record.get("client") in ("claude-code",
                                                                        "codex") else "unknown"
            project = _project(record, key)
            groups[(client, project)] += 1
            if project.startswith("lane:"):
                lane_records.append(path)
        ledger, sink = CustodyLedger(home, owner), sink or default_sink()
        for (client, project), count in sorted(groups.items()):
            fields = {"client": client, "project_ref": project, "count": count}
            entry = ledger.append("capture_suppressed", fields)
            try:
                sink.write("capture_suppressed", event_text(
                    "capture_suppressed", entry["seq"], owner, {"items": count}, "none"))
            except OSError as exc:
                _log.warning("capture-off witness event not written (%s)", type(exc).__name__)
        kept = [p for p in new if p not in lane_records]
        if kept:
            with open(done_path, "a", encoding="ascii") as stream:
                stream.write("".join(p.name + "\n" for p in kept))
        for path in lane_records:          # counted in the ledger; nothing else in it
            try:
                path.unlink()
            except OSError as exc:
                _log.warning("a folded lane suppression record stays (%s)",
                             type(exc).__name__)
    return len(new)
