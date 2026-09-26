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
import json
import os
from pathlib import Path
import re

from .evidence_json import canonical_bytes, canonical_sha256
from .journey_lock import ExclusiveJourneyLock, fsync_directory

SCHEMA = "flywheel.custody-ledger-entry/v1"
HEAD_SCHEMA = "flywheel.custody-ledger-head/v1"
GENESIS = "0" * 64
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
               "destination_digest"} | _PRESENCE,
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
        self.dir = Path(home) / "state" / "custody-ledger" / "v1" / "owners" / owner_ref
        self.path, self.anchor = self.dir / "ledger.jsonl", self.dir / "head.json"
        self.lock_timeout_s = lock_timeout_s

    def append(self, kind: str, fields: dict) -> dict:
        check_fields(kind, fields)
        self.dir.mkdir(parents=True, exist_ok=True)
        _owner_only(self.dir)
        with ExclusiveJourneyLock.acquire(self.dir / ".lock", self.lock_timeout_s):
            entries, report = self._load(repair=True)
            if not report["ok"]:
                raise LedgerError("LEDGER_INVALID")
            head = entries[-1]["entry_sha256"] if entries else GENESIS
            entry = {"schema": SCHEMA, "seq": len(entries), "kind": kind, "at": _now(),
                     "fields": fields, "prior_sha256": head}
            entry["entry_sha256"] = canonical_sha256(entry)
            with self.path.open("ab") as stream:
                stream.write(canonical_bytes(entry) + b"\n")
                stream.flush()
                os.fsync(stream.fileno())
            self._write_anchor(len(entries) + 1, entry["entry_sha256"])
            return entry

    def entries(self) -> list[dict]:
        entries, report = self._load(repair=False)
        if not report["ok"]:
            raise LedgerError(report["reason"])
        return entries

    def verify(self) -> dict:
        return self._load(repair=False)[1]

    def _write_anchor(self, count: int, head: str) -> None:
        temporary = self.anchor.with_name("head.json.tmp")
        temporary.write_bytes(canonical_bytes({"schema": HEAD_SCHEMA, "count": count,
                                               "head_sha256": head}))
        os.replace(temporary, self.anchor)
        fsync_directory(self.dir)

    def _load(self, *, repair: bool) -> tuple[list[dict], dict]:
        raw = self.path.read_bytes() if self.path.exists() else b""
        if raw and not raw.endswith(b"\n"):
            if not repair:
                return [], _bad("TORN_TAIL")
            raw = raw[:raw.rfind(b"\n") + 1]
            with self.path.open("r+b") as stream:
                stream.truncate(len(raw))
        entries, head = [], GENESIS
        for number, line in enumerate(raw.splitlines()):
            try:
                entry = json.loads(line)
                digest = entry.pop("entry_sha256")
            except (ValueError, TypeError, KeyError, AttributeError):
                return [], _bad("ENTRY_UNREADABLE")
            if canonical_sha256(entry) != digest:
                return [], _bad("ENTRY_DIGEST")
            if entry.get("prior_sha256") != head or entry.get("seq") != number:
                return [], _bad("CHAIN_BROKEN")
            entry["entry_sha256"] = head = digest
            entries.append(entry)
        return entries, self._against_anchor(entries, head)

    def _against_anchor(self, entries: list[dict], head: str) -> dict:
        if not self.anchor.exists():
            return (_ok(0, GENESIS, 0) if not entries else _bad("ANCHOR_MISSING"))
        try:
            anchor = json.loads(self.anchor.read_bytes())
            count, anchored = anchor["count"], anchor["head_sha256"]
        except (ValueError, TypeError, KeyError):
            return _bad("ANCHOR_UNREADABLE")
        if type(count) is not int or count > len(entries):
            return _bad("TRUNCATED")
        if count and entries[count - 1]["entry_sha256"] != anchored:
            return _bad("HEAD_MISMATCH")
        return _ok(len(entries), head, len(entries) - count)


def _ok(entries: int, head: str, behind: int) -> dict:
    return {"ok": True, "entries": entries, "head": head, "anchor_behind": behind}


def _bad(reason: str) -> dict:
    return {"ok": False, "reason": reason}


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
        return {**_ok(0, GENESIS, 0), "losses": 0}
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
