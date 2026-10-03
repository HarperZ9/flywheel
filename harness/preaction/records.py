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
REDEEM_SCHEMA = "flywheel.preaction-redeem/v1"
SCHEMAS = (HOLD_SCHEMA, ALLOW_SCHEMA, DECISION_SCHEMA, POST_SCHEMA, REDEEM_SCHEMA)
_TAIL_CHUNK = 65536


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
        self.ctx_dir = self.home / "ctx"

    def read_all(self, *, tolerant: bool = False) -> list:
        """Every record in order. Strict by default; tolerant=True skips a line
        that does not parse (a torn append) and keeps a marker in its place so
        the verifier can report it."""
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                if not tolerant:
                    raise
                out.append({"schema": "unparseable", "source": "torn-line"})
        return out

    def _last_record(self):
        """The last complete record, read from the file's tail so an append
        costs the same on a store of ten records or ten million. A torn final
        line (a writer killed mid-append) is terminated so the next record
        starts on its own line; the verifier reports the torn line as DRIFT."""
        if not self.path.exists():
            return None
        with open(self.path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            end = fh.tell()
            if end == 0:
                return None
            fh.seek(end - 1)
            if fh.read(1) != b"\n":
                with open(self.path, "ab") as fa:
                    fa.write(b"\n")
            pos, buf = end, b""
            while pos > 0:
                step = min(_TAIL_CHUNK, pos)
                pos -= step
                fh.seek(pos)
                buf = fh.read(step) + buf
                lines = [ln for ln in buf.split(b"\n") if ln.strip()]
                usable = lines if pos == 0 else lines[1:]
                for line in reversed(usable):
                    try:
                        return json.loads(line.decode("utf-8"))
                    except ValueError:
                        continue
        return None

    def _head(self) -> tuple:
        last = self._last_record()
        if last is None:
            return "", 0
        return last.get("seal", {}).get("hex", ""), int(last.get("store_seq", 0))

    def append(self, record: dict, raw_args: dict | None = None,
               context: dict | None = None) -> str:
        """Chain, seal and durably write one record. Returns its seal hex."""
        try:
            self.home.mkdir(parents=True, exist_ok=True)
            with ExclusiveJourneyLock.acquire(self.home / ".records.lock", 5.0):
                prev, seq = self._head()
                record.pop("seal", None)
                record["store_seq"] = seq + 1
                record["prev_record_sha256"] = prev
                if context is not None:
                    record["context_sha256"] = _sha256_hex(_canonical_bytes(context))
                hexd = seal(record)
                if context is not None:
                    _private_write(self.ctx_dir / f"{hexd}.json",
                                   json.dumps(context, ensure_ascii=False).encode("utf-8"))
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

    def raw_context(self, seal_hex: str):
        p = self.ctx_dir / f"{seal_hex}.json"
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

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
        "trust_domain": _domain(call.path_id),
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


def _domain(path_id: str) -> str:
    from .coverage import domain_for
    return domain_for(path_id)


def decision_record(*, hold: dict, decision: str, decider: str, decided_at: str,
                    grant_id: str, review_payload_sha256: str, reason_sha256: str = "",
                    reason_code: str = "") -> dict:
    rec = {
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
    if reason_code:
        # Present only when the owner gave a code, so records written before
        # reason codes existed keep their exact shape and seal.
        rec["reason_code"] = reason_code
    return rec


def context_of(ctx) -> dict:
    """The run context the deterministic rules read, so a verifier can re-run
    them. Kept in an owner-only side file; the sealed record carries its digest."""
    return {"workspace": ctx.workspace, "allow_hosts": sorted(ctx.allow_hosts),
            "owned_hosts": sorted(ctx.owned_hosts), "fetch_hosts": sorted(ctx.fetch_hosts),
            "canaries": sorted(ctx.canaries),
            "protected_paths": sorted(ctx.protected_paths)}


def redeem_record(*, call, ctx, hold_id: str, assessment) -> dict:
    """A one-use grant was consumed and the call is about to run."""
    return {"schema": REDEEM_SCHEMA, "source": f"redeem:{ctx.run_id}:{call.tool_use_id}",
            "harness": call.harness, "path_id": call.path_id, "run_id": ctx.run_id,
            "tool": call.tool, "tool_use_id": call.tool_use_id,
            "call_sha256": call.call_sha256(), "hold_id": hold_id,
            "assessed_verdict": assessment.verdict, "rules_digest": assessment.rules_digest,
            "config_sha256": assessment.config_sha256}


def post_record(*, harness: str, run_id: str, tool: str, tool_use_id: str,
                args_sha256: str, observed_at: str) -> dict:
    return {"schema": POST_SCHEMA, "source": f"post:{run_id}:{tool_use_id}",
            "harness": harness, "run_id": run_id, "tool": tool, "tool_use_id": tool_use_id,
            "args_sha256": args_sha256, "observed_at": observed_at}
