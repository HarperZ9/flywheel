"""records.py -- sealed, chained pre-action records, written before the call.

One append-only store per monitor home (records.jsonl). Every record is built
in a fixed field order with no floats, sealed with sha256 over its canonical
bytes (the tool-call receipt rules), and linked to the previous record by
prev_record_sha256 and a store sequence number. A record carries digests,
never raw arguments. Raw arguments go to an owner-only side file keyed by the
record seal, so the owner (or a stranger the owner hands it to) can re-derive
the deterministic verdict.

Unlike emit_receipt, which never raises, this writer fails closed: if the
record cannot be written, append raises RecordWriteError and the caller must
not run the call.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from ..journey_lock import ExclusiveJourneyLock
from ..tool_call_receipt import _canonical_bytes, _sha256_hex

HOLD_SCHEMA = "flywheel.preaction-hold/v1"
ALLOW_SCHEMA = "flywheel.preaction-allow/v1"
DECISION_SCHEMA = "flywheel.preaction-decision/v1"
POST_SCHEMA = "flywheel.preaction-post/v1"
SCHEMAS = (HOLD_SCHEMA, ALLOW_SCHEMA, DECISION_SCHEMA, POST_SCHEMA)


class RecordWriteError(RuntimeError):
    """The sealed record could not be written; the call must not run."""


def seal(record: dict) -> str:
    record["seal"] = {"algorithm": "sha256", "hex": ""}
    record["seal"]["hex"] = _sha256_hex(_canonical_bytes(record))
    return record["seal"]["hex"]


def verify_seal(record: dict) -> bool:
    s = record.get("seal")
    if not isinstance(s, dict) or s.get("algorithm") != "sha256":
        return False
    probe = dict(record)
    probe["seal"] = {"algorithm": "sha256", "hex": ""}
    return _sha256_hex(_canonical_bytes(probe)) == s.get("hex")


def _private_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())


class HoldStore:
    def __init__(self, home) -> None:
        self.home = Path(home)
        self.path = self.home / "records.jsonl"
        self.args_dir = self.home / "args"

    def read_all(self) -> list:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
        return out

    def _head(self) -> tuple:
        recs = self.read_all()
        if not recs:
            return "", 0
        return recs[-1].get("seal", {}).get("hex", ""), int(recs[-1].get("store_seq", 0))

    def append(self, record: dict, raw_args: dict | None = None) -> str:
        """Chain, seal and durably write one record. Returns its seal hex."""
        try:
            self.home.mkdir(parents=True, exist_ok=True)
            with ExclusiveJourneyLock.acquire(self.home / ".records.lock", 5.0):
                prev, seq = self._head()
                record.pop("seal", None)
                record["store_seq"] = seq + 1
                record["prev_record_sha256"] = prev
                hexd = seal(record)
                if raw_args is not None:
                    _private_write(self.args_dir / f"{hexd}.json",
                                   json.dumps(raw_args, ensure_ascii=False).encode("utf-8"))
                line = json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n"
                with open(self.path, "a", encoding="utf-8") as fh:
                    fh.write(line)
                    fh.flush()
                    os.fsync(fh.fileno())
            return hexd
        except RecordWriteError:
            raise
        except Exception as exc:  # noqa: BLE001 -- any failure means the call does not run
            raise RecordWriteError(f"{type(exc).__name__}: {exc}") from exc

    def raw_args(self, seal_hex: str):
        p = self.args_dir / f"{seal_hex}.json"
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))


def assessment_record(*, call, ctx, assessment, trajectory_sha256: str, expires_at: str,
                      owner_ref: str, does_not_prove: str) -> dict:
    """The hold (HOLD or BLOCK) or allow record, fields in fixed order."""
    args_bytes = call.args_bytes()
    schema = ALLOW_SCHEMA if assessment.verdict == "ALLOW" else HOLD_SCHEMA
    block = assessment.preaction_block()
    return {
        "schema": schema,
        "source": f"hold:{ctx.run_id}:{call.seq}",
        "harness": call.harness,
        "path_id": call.path_id,
        "run_id": ctx.run_id,
        "tool": call.tool,
        "tool_use_id": call.tool_use_id,
        "capability": call.capability_class(),
        "args": {"sha256": _sha256_hex(args_bytes), "bytes": len(args_bytes)},
        "call_sha256": call.call_sha256(),
        "goal_sha256": ctx.goal_sha256(),
        "trajectory_sha256": trajectory_sha256,
        "verdict": assessment.verdict,
        "coverage": assessment.coverage,
        "rules_digest": assessment.rules_digest,
        "rule_hits": block["rule_hits"],
        "trajectory_hits": block["trajectory_hits"],
        "judge": block["judge"],
        "config_sha256": assessment.config_sha256,
        "config_pin": assessment.config_pin,
        "hold_id": assessment.hold_id,
        "expires_at": expires_at,
        "owner_ref": owner_ref,
        "does_not_prove": does_not_prove,
    }


def decision_record(*, hold: dict, decision: str, decider: str, decided_at: str,
                    grant_id: str, review_payload_sha256: str, reason_sha256: str = "") -> dict:
    return {
        "schema": DECISION_SCHEMA,
        "source": f"decision:{hold.get('hold_id', '')}",
        "hold_id": hold.get("hold_id", ""),
        "hold_record_sha256": hold["seal"]["hex"],
        "decision": decision,
        "decider": decider,
        "decided_at": decided_at,
        "grant_id": grant_id,
        "review_payload_sha256": review_payload_sha256,
        "reason_sha256": reason_sha256,
    }


def post_record(*, harness: str, run_id: str, tool: str, tool_use_id: str,
                args_sha256: str, observed_at: str) -> dict:
    return {"schema": POST_SCHEMA, "source": f"post:{run_id}:{tool_use_id}",
            "harness": harness, "run_id": run_id, "tool": tool, "tool_use_id": tool_use_id,
            "args_sha256": args_sha256, "observed_at": observed_at}
