"""Retention runs (7.4, I6): plan first, then deletion through the engine.

A run reads the adopted policy. Keep does nothing and writes nothing. Under
rules, the run selects the items the rules name and hands them to the
deletion engine (7.10) as a saved plan. The first run after an adoption that
finds something due only plans; whether that preview happened is read from
the verified custody ledger (a `retention_run` entry with reason
`first_run_plan_only` after the adoption), never from a file. A later run whose plan would delete more than `max_share_per_run` of
any store's items stops at the plan, which stays pending until the owner
applies it with presence; otherwise the run applies its plan under the
adopted policy's authority, with the same closure, verification and
tombstone as a manual delete. Each run writes one custody ledger entry and
one witness event. A failed run keeps its plan pending and shows in status.

The gateway starts the scheduler only when an adopted rule other than keep
exists at gateway start; it runs then and every 24 hours. A policy adopted
while the gateway runs takes effect from the next gateway start, and status
says whether the running scheduler has picked it up.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import threading
import time

from . import trace_retention as policy
from .evidence_json import canonical_bytes

_log = logging.getLogger(__name__)
INTERVAL_S = 24 * 3600
METHOD = "retention-policy"
_KEYS = {"S1": "trace_refs", "CT": "turn_refs", "IM": "import_refs"}


def _state_path(home, owner: str) -> Path:
    return Path(home) / "state" / "trace-retention" / "v1" / "owners" / owner / "runs.json"


def _load(home, owner: str) -> dict:
    try:
        return json.loads(_state_path(home, owner).read_bytes())
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        _log.warning("retention run state unreadable (%s); runs start over at plan-only",
                     type(exc).__name__)
        return {}


def _save(home, owner: str, doc: dict) -> None:
    from .trace_custody_lock import custody_lock
    path = _state_path(home, owner)
    with custody_lock(Path(home) / "state"):
        from . import trace_durable
        trace_durable.write_durable(path, canonical_bytes(doc))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def should_schedule(home, owner: str) -> bool:
    return policy.adopted(home, owner)["action"] != "keep"


def _record(home, owner: str, result: dict, method: str, sink) -> dict:
    from .trace_witness import record_custody_event
    fields = {"plan_digest": result.get("plan_digest"), "items": result.get("items", 0),
              "applied": result["state"] == "APPLIED", "reason_code": result["reason"]}
    return record_custody_event(Path(home), owner, "retention_run", fields, method, sink=sink)


def _apply(home, owner: str, digest: str, method: str, sink) -> dict:
    from . import trace_delete_apply
    try:
        report = trace_delete_apply.apply_authorized(home, owner, digest, method,
                                                     reason="retention", sink=sink,
                                                     record=False)
    except Exception as exc:  # a scheduled run must report, not die; logged below
        _log.exception("retention apply failed for plan %s", digest[:12])
        return {"state": "FAILED", "reason": getattr(exc, "code", type(exc).__name__)}
    if report["state"] != "DELETED":
        return {"state": "FAILED", "reason": report.get("reason") or report["state"]}
    return {"state": "APPLIED", "reason": "retention"}


def _plan(home, owner: str, doc: dict, now: float) -> dict:
    from .trace_delete_plan import make_plan
    chosen, share = policy.select(doc, policy.items(home, owner), now)
    if not chosen:
        return {"plan_digest": None, "items": 0, "share": {}}
    plan = make_plan(home, owner, {_KEYS[s]: refs for s, refs in chosen.items()})
    return {"plan_digest": plan["plan_digest"], "items": sum(map(len, chosen.values())),
            "share": share}


def previewed(home, owner: str, policy_digest: str) -> bool:
    """Whether a plan-only run happened under the current adoption of this
    policy, read from the verified ledger. An unverifiable ledger says no."""
    from .trace_custody_ledger import CustodyLedger, LedgerError
    try:
        entries = CustodyLedger(home, owner).entries()
    except LedgerError:
        return False
    current, shown = None, False
    for entry in entries:
        fields = entry["fields"]
        if entry["kind"] == "settings_adopted" and fields.get("settings") == "retention":
            current, shown = fields.get("digest"), False
        elif entry["kind"] == "retention_run" and fields.get("reason_code") == \
                "first_run_plan_only":
            shown = True
    return current == policy_digest and shown


def _decide(home, owner: str, doc: dict, runs: dict, planned: dict, sink) -> dict:
    if planned["plan_digest"] is None:
        return {"state": "NOTHING_DUE", "reason": "nothing_due"}
    if not previewed(home, owner, policy.digest(doc)):
        return {"state": "PLANNED", "reason": "first_run_plan_only"}
    if any(v > doc["max_share_per_run"] for v in planned["share"].values()):
        return {"state": "STOPPED_AT_PLAN", "reason": "share_exceeded"}
    return _apply(home, owner, planned["plan_digest"], METHOD, sink)


def run(home, owner: str, *, now: float | None = None, sink=None) -> dict:
    """One retention run under the adopted policy."""
    doc = policy.adopted(home, owner)
    if doc["action"] == "keep":
        return {"state": "KEEP"}
    runs = _load(home, owner)
    planned = _plan(home, owner, doc, now or time.time())
    result = {**planned, **_decide(home, owner, doc, runs, planned, sink)}
    pending = None if result["state"] in ("APPLIED", "NOTHING_DUE") else {
        "plan_digest": planned["plan_digest"], "items": planned["items"],
        "share": planned["share"], "reason": result["reason"], "created_at": _now_iso()}
    _save(home, owner, {**{k: v for k, v in runs.items() if k == "scheduler"},
                        "pending_plan": pending,
                        "last_run": {"state": result["state"], "reason": result["reason"],
                                     "at": _now_iso()}})
    result["witness"] = _record(home, owner, result, METHOD, sink)["witness"]
    return result


def plan_now(home, owner: str, *, now: float | None = None) -> dict:
    """The plan the adopted policy gives now, kept pending for an owner apply.
    It deletes nothing and is not a run, so it writes no ledger entry."""
    doc = policy.adopted(home, owner)
    if doc["action"] == "keep":
        return {"state": "KEEP"}
    planned = _plan(home, owner, doc, now or time.time())
    if planned["plan_digest"] is None:
        return {"state": "NOTHING_DUE", **planned}
    runs = _load(home, owner)
    runs["pending_plan"] = {**planned, "reason": "owner_plan", "created_at": _now_iso()}
    _save(home, owner, runs)
    return {"state": "PLANNED", **planned}


def apply_pending(home, owner: str, plan_digest: str, presence_ref, *, sink=None) -> dict:
    """The owner applies the pending plan with presence bound to its digest."""
    from .trace_presence import require
    runs = _load(home, owner)
    pending = runs.get("pending_plan")
    if not pending or pending["plan_digest"] != plan_digest:
        return {"state": "PLAN_NOT_PENDING"}
    method = require(Path(home) / "state", owner, "retention_apply", plan_digest,
                     presence_ref)
    result = {**_apply(home, owner, plan_digest, method, sink), "plan_digest": plan_digest,
              "items": pending["items"]}
    if result["state"] == "APPLIED":
        runs["pending_plan"] = None
    runs["last_run"] = {"state": result["state"], "reason": result["reason"],
                        "at": _now_iso()}
    _save(home, owner, runs)
    result["witness"] = _record(home, owner, result, method, sink)["witness"]
    return result


def status(home, owner: str) -> dict:
    """`scheduled` is true only when a gateway scheduler started under the
    policy in effect; otherwise the rules run from the next gateway start."""
    runs = _load(home, owner)
    current = policy.effective(home, owner)
    started = runs.get("scheduler") or {}
    scheduled = current["action"] != "keep" and started.get("policy") == current["digest"]
    return {"action": current["action"], "rules": len(current["rules"]),
            "pending_change": current["pending_change"], "file_valid": current["file_valid"],
            "tampered": current.get("tampered", False),
            "pending_plan": runs.get("pending_plan"), "last_run": runs.get("last_run"),
            "scheduled": scheduled,
            "scheduler_started_at": started.get("at") if scheduled else None}


def needs_owner(home, owner: str) -> bool:
    """A policy change or a plan waits for the owner (the prompt hook says so)."""
    shown = status(home, owner)
    return bool(shown["pending_change"] or shown["pending_plan"] or shown["tampered"])


class Scheduler:
    """Runs retention at start and every 24 hours on a daemon thread."""

    def __init__(self, home, owner: str, interval_s: float = INTERVAL_S) -> None:
        self.home, self.owner, self.interval_s = Path(home), owner, interval_s
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._loop, name="flywheel-retention",
                                       daemon=True)

    def _loop(self) -> None:
        while not self.stop.is_set():
            try:
                result = run(self.home, self.owner)
                _log.info("retention run: %s (%s)", result["state"], result.get("reason"))
            except Exception:  # logged; the next run retries
                _log.exception("retention run failed")
            self.stop.wait(self.interval_s)


def start_if_adopted(home) -> Scheduler | None:
    """Gateway start hook: a scheduler only for an adopted rule other than keep."""
    from .trace_custody_ledger import read_owner_ref
    owner = read_owner_ref(home)
    if owner is None or not should_schedule(home, owner):
        return None
    scheduler = Scheduler(home, owner)
    runs = _load(home, owner)
    runs["scheduler"] = {"policy": policy.digest(policy.adopted(home, owner)),
                         "at": _now_iso()}
    _save(home, owner, runs)
    scheduler.thread.start()
    return scheduler
