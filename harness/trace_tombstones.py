"""The deletion ledger: one tombstone per verified deletion (7.10, SP-18, I5).

A tombstone holds a random ref, the plan digest, the stores touched, counts
per data class, the reason code, start and verification times, residual scan
hits per store, residue classes with counts, out-of-reach classes with counts,
the checks that ran and the presence method. It holds no content, no content
digest, no path and no session id: every value must be a count or a short
token from a fixed grammar, and a token that looks like a path or a UUID is
refused, so nothing written after a deletion can confirm a guess of what was
deleted or link the project and session it came from.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
import secrets

from .trace_chain_log import ChainedLog

SCHEMA = "flywheel.trace-tombstone/v1"
HEAD_SCHEMA = "flywheel.trace-tombstone-head/v1"
_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_.\-]{0,63}\Z")
_UUIDISH = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-", re.I)
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_TIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")


class TombstoneError(ValueError):
    def __init__(self, code: str = "TOMBSTONE_INVALID") -> None:
        super().__init__(code)
        self.code = code


def _token(value) -> bool:
    return type(value) is str and bool(_TOKEN.fullmatch(value)) and not _UUIDISH.search(value)


def _counts(value) -> bool:
    return type(value) is dict and len(value) <= 64 and all(
        _token(k) and type(v) is int and v >= 0 for k, v in value.items())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def check(fields: dict) -> None:
    ok = (_DIGEST.fullmatch(str(fields.get("plan_digest", "")))
          and type(fields.get("stores")) is list and len(fields["stores"]) <= 64
          and all(_token(s) for s in fields["stores"])
          and all(_counts(fields.get(k)) for k in ("counts", "residual", "residue",
                                                    "out_of_reach"))
          and _token(fields.get("reason_code")) and _token(fields.get("presence"))
          and type(fields.get("checks")) is list and all(_token(c) for c in fields["checks"])
          and _TIME.fullmatch(str(fields.get("started_at", ""))))
    if not ok:
        raise TombstoneError()


class TombstoneLedger:
    def __init__(self, state_root, owner_ref: str) -> None:
        directory = Path(state_root) / "trace-deletions" / "v1" / "owners" / owner_ref
        self.log = ChainedLog(directory, "tombstones", SCHEMA, HEAD_SCHEMA)
        self.path = self.log.path

    def append(self, *, plan_digest, stores, counts, reason_code, started_at, residual,
               residue, out_of_reach, presence, checks) -> dict:
        fields = {"plan_digest": plan_digest, "stores": list(stores), "counts": dict(counts),
                  "reason_code": reason_code, "started_at": started_at,
                  "residual": dict(residual), "residue": dict(residue),
                  "out_of_reach": dict(out_of_reach), "presence": presence,
                  "checks": list(checks)}
        check(fields)
        body = {**fields, "tombstone_ref": "tomb_" + secrets.token_hex(16),
                "verified_at": _now()}
        return self.log.append_body(body, invalid=TombstoneError("LEDGER_INVALID"))

    def entries(self) -> list[dict]:
        return self.log.entries(invalid=TombstoneError("LEDGER_INVALID"))

    def verify(self) -> dict:
        return self.log.verify()
