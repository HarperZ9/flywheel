"""The custody ledger: hash-chained, metadata-only custody events (7.14, I15).

Each custody event (a capture count, a suppression, a settings adoption, an
import, an export, a retention run, a deletion, a loss) appends one JSON line
whose digest chains to the line before. A head anchor beside the ledger holds
the count and the last digest, so a truncated ledger is caught, the method
mneme uses for its audit log. Truncating both files consistently is not
caught here; the witness (7.15) exists for that.

No entry can carry content. Each kind has an allowlist of keys, and every
value is a count, a flag, or a short token (codes, store ids, hex digests,
timestamps): no spaces, no path separators, at most 128 characters.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re

from .journey_lock import ExclusiveJourneyLock
from .trace_chain_log import GENESIS, ChainedLog, ok

SCHEMA = "flywheel.custody-ledger-entry/v1"
HEAD_SCHEMA = "flywheel.custody-ledger-head/v1"
_OWNER = re.compile(r"owner_[0-9a-f]{32}\Z")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:\-]{0,127}\Z")
_PRESENCE = {"presence"}
KINDS = {
    "loss": {"store", "items", "reason_code", "original"},
    "capture_count": {"client", "turns", "failures", "suppressed"},
    "capture_suppressed": {"client", "project_ref", "count"},
    "capture_failure": {"client", "reason_code", "count"},
    "settings_adopted": {"settings", "digest"} | _PRESENCE,
    "import": {"client", "items", "bytes", "skipped", "refused"} | _PRESENCE,
    "export": {"root_digest", "items", "bytes", "stores", "redaction",
               "destination_digest", "reason_code"} | _PRESENCE,
    "retention_run": {"plan_digest", "items", "applied", "reason_code"} | _PRESENCE,
    "deletion": {"plan_digest", "stores", "items", "reason_code", "residue",
                 "out_of_reach"} | _PRESENCE,
}


class LedgerError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _scalar(value) -> bool:
    if value is None or type(value) is bool:
        return True
    if type(value) is int:
        return value >= 0
    return type(value) is str and _TOKEN.fullmatch(value) is not None


def _metadata(value) -> bool:
    if type(value) is list:
        return len(value) <= 64 and all(_scalar(v) for v in value)
    if type(value) is dict:
        return len(value) <= 64 and all(
            type(k) is str and _TOKEN.fullmatch(k) and _scalar(v) for k, v in value.items())
    return _scalar(value)


def check_fields(kind: str, fields) -> None:
    """Refuse an unknown kind, a key outside its allowlist, or any free text."""
    if kind not in KINDS or type(fields) is not dict:
        raise LedgerError("LEDGER_KIND")
    if not set(fields) <= KINDS[kind]:
        raise LedgerError("LEDGER_KEYS")
    if not all(_metadata(v) for v in fields.values()):
        raise LedgerError("LEDGER_VALUE")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class CustodyLedger:
    def __init__(self, home, owner_ref: str, *, lock_timeout_s: float = 5.0) -> None:
        if type(owner_ref) is not str or _OWNER.fullmatch(owner_ref) is None:
            raise LedgerError("OWNER_INVALID")
        directory = Path(home) / "state" / "custody-ledger" / "v1" / "owners" / owner_ref
        self.log = ChainedLog(directory, "ledger", SCHEMA, HEAD_SCHEMA, anchor="head.json",
                              lock_timeout_s=lock_timeout_s)
        self.dir, self.path, self.anchor = self.log.dir, self.log.path, self.log.anchor
        self.lock_timeout_s = lock_timeout_s

    def append(self, kind: str, fields: dict) -> dict:
        check_fields(kind, fields)
        return self.log.append_body({"kind": kind, "at": _now(), "fields": fields},
                                    invalid=LedgerError("LEDGER_INVALID"))

    def entries(self) -> list[dict]:
        report = self.log.verify()
        if not report["ok"]:
            raise LedgerError(report["reason"])
        return self.log.entries()

    def verify(self) -> dict:
        return self.log.verify()


def _owner_only(directory: Path) -> None:
    from .operation_grants import _secure_owner_only
    _secure_owner_only(directory, directory=True)


def read_owner_ref(home) -> str | None:
    """The owner identity, read without creating it (status stays read-only)."""
    try:
        value = (Path(home) / "owner.ref").read_text(encoding="ascii")
    except (OSError, UnicodeError):
        return None
    return value if _OWNER.fullmatch(value) else None


def ledger_for(home) -> CustodyLedger | None:
    owner = read_owner_ref(home)
    return CustodyLedger(home, owner) if owner else None


def ledger_summary(home) -> dict:
    ledger = ledger_for(home)
    if ledger is None:
        return {**ok(0, GENESIS, 0), "losses": 0}
    report = ledger.verify()
    losses = sum(1 for e in ledger.entries() if e["kind"] == "loss") if report["ok"] else 0
    return {**report, "losses": losses}


def record_loss(home, store: str, items: int, reason_code: str, original: str) -> dict:
    """I1: write the loss record before the loss takes effect."""
    from .operation_grants import load_or_create_owner_ref
    ledger = CustodyLedger(home, load_or_create_owner_ref(Path(home)))
    return ledger.append("loss", {"store": store, "items": items,
                                  "reason_code": reason_code, "original": original})


def export_records(home) -> list[dict]:
    """Export adapter: the verified entries, metadata only."""
    ledger = ledger_for(home)
    return ledger.entries() if ledger else []


def delete_all(home) -> dict:
    """Delete adapter for a whole-custody deletion: the ledger and its anchor."""
    ledger = ledger_for(home)
    if ledger is None or not ledger.dir.exists():
        return {"removed": 0}
    removed = 0
    with ExclusiveJourneyLock.acquire(ledger.dir / ".lock", ledger.lock_timeout_s):
        for path in (ledger.path, ledger.anchor):
            if path.exists():
                path.unlink()
                removed += 1
    return {"removed": removed}
