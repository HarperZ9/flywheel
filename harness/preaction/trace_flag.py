"""trace_flag.py -- a flagged trajectory raises a hold in the pre-action monitor.

The trace-observation layer reads a run's reasoning records and tool calls
after the fact. When one of its rules fires, it calls raise_trace_flag. That
writes one sealed record into the monitor's own chain (records.jsonl, the same
store every hold and allow record lives in) and registers the flag in the
escalator index under the monitor's lock. On the run's next proposed call the
trajectory layer reads the flag and holds the call, so the owner reviews the
flagged trajectory before the agent acts again. The flag clears when the
owner decides a hold that cited it (approve once, reject or terminate). Expiry
leaves it standing, because silence is never yes.

The flag files live in the monitor home, which the monitor always treats as
protected state, so an agent cannot clear its own flag by writing them.

A flag is a behavioral observation over text and actions. It says nothing about
intent; the record carries that line.
"""
from __future__ import annotations

import re

from ..journey_lock import ExclusiveJourneyLock
from .contract import HOLD, Hit, canonical_json, sha256_hex
from .escalate import Escalator
from .records import HoldStore

TRACEFLAG_SCHEMA = "flywheel.preaction-traceflag/v1"
FAMILY = "trace-flag"
FLAG_DOES_NOT_PROVE = (
    "A trace rule matched the run's recorded reasoning or actions. It says nothing "
    "about intent; reasoning text is sampled output, and a summary channel is a "
    "second model's writing. The task, instructions and environment explain the behavior.")
_CLEARING = ("APPROVED_ONCE", "REJECTED", "TERMINATED")
_SAFE = re.compile(r"[^A-Za-z0-9_.-]")


def flag_id_for(run_id: str, rule_id: str, evidence_sha256: str) -> str:
    return "tf_" + sha256_hex(f"{run_id}:{rule_id}:{evidence_sha256}".encode())[:16]


def traceflag_record(*, run_id: str, flag_id: str, rule_id: str, channel: str,
                     access_class: str, evidence_sha256: str,
                     observation_receipt_sha256: str, raised_at: str) -> dict:
    """Fixed field order, strings only, digests in place of reasoning text."""
    return {
        "schema": TRACEFLAG_SCHEMA,
        "source": f"traceflag:{run_id}:{flag_id}",
        "run_id": run_id,
        "flag_id": flag_id,
        "rule_id": rule_id,
        "channel": channel,
        "access_class": access_class,
        "evidence_sha256": evidence_sha256,
        "observation_receipt_sha256": observation_receipt_sha256,
        "raised_at": raised_at,
        "does_not_prove": FLAG_DOES_NOT_PROVE,
    }


def raise_trace_flag(home, *, run_id: str, rule_id: str, channel: str, access_class: str,
                     evidence_sha256: str, raised_at: str,
                     observation_receipt_sha256: str = "") -> dict:
    """Record the flag in the monitor chain, then register it for the next call.

    The sealed record is written first; if it cannot be written the flag is not
    registered and RecordWriteError propagates, so a caller never believes a
    hold is armed when no record backs it.
    """
    if not run_id:
        raise ValueError("raise_trace_flag: run_id is required")
    flag_id = flag_id_for(run_id, rule_id, evidence_sha256)
    rec = traceflag_record(run_id=run_id, flag_id=flag_id, rule_id=_SAFE.sub("_", rule_id),
                           channel=channel, access_class=access_class,
                           evidence_sha256=evidence_sha256,
                           observation_receipt_sha256=observation_receipt_sha256,
                           raised_at=raised_at)
    seal_hex = HoldStore(home).append(rec)
    esc = Escalator(home, clock=lambda: raised_at)
    with ExclusiveJourneyLock.acquire(esc.home / ".pending.lock", 5.0):
        index = esc._read_index()
        flags = index.setdefault("trace_flags", {}).setdefault(run_id, {})
        flags[flag_id] = {"rule_id": rec["rule_id"], "channel": channel,
                          "access_class": access_class, "record_sha256": seal_hex}
        esc._write_index(index)
    return {"flag_id": flag_id, "record_sha256": seal_hex}


def active_flags(index: dict, run_id: str) -> dict:
    return dict(index.get("trace_flags", {}).get(run_id, {}))


def flag_hits(flags: dict) -> list:
    """One HOLD hit per active flag, in a stable order, at the trajectory layer."""
    out = []
    for flag_id in sorted(flags):
        f = flags[flag_id]
        out.append(Hit(f"{FAMILY}/{flag_id}", FAMILY, HOLD,
                       f"Trace observation flagged this run ({f.get('rule_id', '')}, "
                       f"{f.get('channel', '')} channel); the owner reviews it before the next call.",
                       layer=2))
    return out


def clear_on_decision(index: dict, pending: dict, decision: str) -> list:
    """Remove the flags a decided hold cited. Returns the cleared flag ids."""
    if decision not in _CLEARING:
        return []
    run_flags = index.get("trace_flags", {}).get(pending.get("run_id", ""), {})
    cleared = []
    for reason in pending.get("reasons", []):
        if reason.get("family") != FAMILY:
            continue
        flag_id = str(reason.get("id", "")).split("/", 1)[-1]
        if run_flags.pop(flag_id, None) is not None:
            cleared.append(flag_id)
    return cleared


def evidence_digest(parts: list) -> str:
    return sha256_hex(canonical_json(parts))
