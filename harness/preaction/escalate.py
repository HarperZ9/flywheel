"""escalate.py -- hold, ask the owner, act on the answer. Silence is never yes.

A hold files a one-use grant proposal for exactly that call (keyed by the
normalized call_sha256) and waits. The owner approves once, rejects, or lets
it expire; every decision is a sealed record chained to the hold. An approval
admits exactly one identical call: a re-issued call whose arguments differ
gets a new hold, and the grant is consumed on redemption. Reject is durable
(the call is blocked if asked again); terminate ends the run; expiry is
recorded as EXPIRED and the call never runs.

Operational state (which holds are open, which grants are unconsumed) lives in
an index file; the sealed chain in records.jsonl is the audit trail a stranger
re-walks. Both are owner-only.
"""
from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

from ..journey_lock import ExclusiveJourneyLock
from .contract import REVIEW_DOES_NOT_PROVE
from .records import HoldStore, decision_record

_DECISIONS = ("APPROVED_ONCE", "REJECTED", "TERMINATED", "EXPIRED")


def review_payload(pending: dict) -> dict:
    """What the owner sees, in the fixed order, before any approve control."""
    return {
        "proposed_action": pending["proposed_action"],
        "reasons": pending["reasons"],
        "goal_and_trajectory": pending.get("goal_and_trajectory", {}),
        "coverage": pending.get("coverage", {}),
        "does_not_prove": REVIEW_DOES_NOT_PROVE,
        "expiry_and_owner": {"expires_at": pending.get("expires_at", ""),
                             "owner_ref": pending.get("owner_ref", "")},
        "confirm_code": pending.get("confirm_code", ""),
    }


class TtyApprover:
    """An in-loop approver that only works at a real terminal and needs the
    typed confirmation code. An agent's shell has no tty, so it cannot self-approve."""

    def __init__(self, read=input, write=print, isatty=None) -> None:
        import sys
        self.read, self.write = read, write
        self.isatty = isatty or (lambda: sys.stdin.isatty() and sys.stdout.isatty())

    def __call__(self, payload: dict) -> str | None:
        if not self.isatty():
            return None
        pa = payload.get("proposed_action", {})
        self.write(f"HOLD {pa.get('tool', '')} {json.dumps(pa.get('args', {}))[:400]}")
        for r in payload.get("reasons", []):
            self.write(f"  [{r.get('family', '')}] {r.get('reason', '')}")
        self.write(payload.get("does_not_prove", ""))
        self.write(f"Type the code to approve once, anything else cancels: {payload['confirm_code']}")
        self.read("decision> ")
        typed = self.read("code> ")
        return "APPROVED_ONCE" if typed.strip() == payload["confirm_code"] else None


class Escalator:
    def __init__(self, home, clock, owner_ref: str = "owner_local") -> None:
        self.home = Path(home)
        self.clock, self.owner_ref = clock, owner_ref
        self.store = HoldStore(home)
        self.index_path = self.home / "pending.json"

    # --- index helpers -----------------------------------------------------
    def _read_index(self) -> dict:
        if not self.index_path.exists():
            return {"pending": {}, "grants": {}, "rejected": [], "terminated": []}
        return json.loads(self.index_path.read_text(encoding="utf-8"))

    def _write_index(self, index: dict) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        tmp = self.index_path.with_name(f".pending.{os.getpid()}.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(index, fh)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.index_path)

    # --- filing a hold -----------------------------------------------------
    def file(self, hold_record: dict, *, proposed_action: dict, reasons: list,
             goal_and_trajectory: dict, coverage: dict, expires_at: str) -> dict:
        with ExclusiveJourneyLock.acquire(self.home / ".pending.lock", 5.0):
            index = self._read_index()
            pending = {
                "hold_id": hold_record["hold_id"],
                "run_id": hold_record["run_id"],
                "call_sha256": hold_record["call_sha256"],
                "hold_record_sha256": hold_record["seal"]["hex"],
                "verdict": hold_record["verdict"],
                "proposed_action": proposed_action,
                "reasons": reasons,
                "goal_and_trajectory": goal_and_trajectory,
                "coverage": coverage,
                "expires_at": expires_at,
                "owner_ref": self.owner_ref,
                "confirm_code": secrets.token_hex(3),
            }
            index["pending"][hold_record["hold_id"]] = pending
            self._write_index(index)
        return pending

    def pending(self) -> list:
        return list(self._read_index()["pending"].values())

    def read_pending(self, hold_id: str) -> dict:
        return self._read_index()["pending"][hold_id]

    # --- the owner decides -------------------------------------------------
    def decide(self, hold_id: str, decision: str, *, decider: str, reason: str = "") -> dict:
        if decision not in _DECISIONS:
            raise ValueError(f"decision must be one of {_DECISIONS}")
        with ExclusiveJourneyLock.acquire(self.home / ".pending.lock", 5.0):
            index = self._read_index()
            if hold_id not in index["pending"]:
                raise ValueError(f"no open hold {hold_id}")
            pending = index["pending"].pop(hold_id)
            hold = self._find_hold(pending["hold_record_sha256"])
            now = self.clock()
            grant_id = ""
            if decision == "APPROVED_ONCE":
                grant_id = "gnt_" + secrets.token_hex(16)
                index["grants"][grant_id] = {
                    "run_id": pending["run_id"], "call_sha256": pending["call_sha256"],
                    "hold_id": hold_id, "consumed": False,
                    "expires_at": self._grant_expiry(now)}
                if any(r.get("family") == "denial-counter" for r in pending.get("reasons", [])):
                    resumed = index.setdefault("resumed", {})
                    resumed[pending["run_id"]] = int(resumed.get(pending["run_id"], 0)) + 1
            elif decision == "REJECTED":
                index["rejected"].append(pending["call_sha256"])
            elif decision == "TERMINATED":
                index["terminated"].append(pending["run_id"])
            from .contract import canonical_json, sha256_hex
            review_sha = sha256_hex(canonical_json(review_payload(pending)))
            rec = decision_record(hold=hold, decision=decision, decider=decider,
                                  decided_at=now, grant_id=grant_id,
                                  review_payload_sha256=review_sha,
                                  reason_sha256=sha256_hex(reason.encode()) if reason else "")
            self.store.append(rec)
            self._write_index(index)
        return {"decision": decision, "grant_id": grant_id}

    def expire_due(self) -> list:
        now = self.clock()
        expired = [p["hold_id"] for p in self.pending() if now >= p["expires_at"]]
        for hold_id in expired:
            self.decide(hold_id, "EXPIRED", decider="system:expiry")
        return expired

    # --- redemption at the next identical call -----------------------------
    def redeem(self, call_sha256: str, run_id: str) -> str | None:
        with ExclusiveJourneyLock.acquire(self.home / ".pending.lock", 5.0):
            index = self._read_index()
            now = self.clock()
            for grant_id, g in index["grants"].items():
                if (not g["consumed"] and g["call_sha256"] == call_sha256
                        and g["run_id"] == run_id and now < g["expires_at"]):
                    g["consumed"] = True
                    self._write_index(index)
                    return g["hold_id"]
        return None

    def is_rejected(self, call_sha256: str) -> bool:
        return call_sha256 in self._read_index()["rejected"]

    def is_terminated(self, run_id: str) -> bool:
        return run_id in self._read_index()["terminated"]

    def _grant_expiry(self, now: str) -> str:
        from datetime import datetime, timedelta, timezone
        dt = datetime.fromisoformat(now.replace("Z", "+00:00")) + timedelta(seconds=300)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    def _find_hold(self, seal_hex: str) -> dict:
        for rec in reversed(self.store.read_all()):
            if rec.get("seal", {}).get("hex") == seal_hex:
                return rec
        raise ValueError("hold record not found for decision")
