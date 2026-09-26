"""Apply a deletion plan (7.10, I4, I14, I17).

Apply recomputes the plan from the saved selection and refuses it when the
digest differs (PLAN_DRIFTED), then requires presence bound to the digest.
A gateway trace whose run still holds its writer lock stops the deletion
before anything is touched (ITEM_BUSY). Under the custody lock and the
deletion journal: running stores drop cached copies, item keys are
destroyed (the keystore rewrite is written through), then files are removed
by handle, then the result is verified (files and keys absent). Only then is
a tombstone written, and a custody ledger entry and a witness event name the
deletion. The report names every copy outside reach and every residue.
"""
from __future__ import annotations

from pathlib import Path

from .journey_lock import ExclusiveJourneyLock, JourneyLockBusy
from .private_artifact_remove import remove
from .trace_custody_lock import custody_lock
from .trace_delete_journal import DeletionJournal, apply_journaled
from .trace_delete_plan import PlanError, drop_selection, load_selection, make_plan

INVALIDATORS: list = []
_CLASSES = {"S1": ("C1", "C2", "C4", "C5"), "CT": ("C1", "C4", "C5"), "S8b": ("C1", "C4")}


def register_invalidator(fn) -> None:
    """A running store registers how to drop its cached copies (SP-15)."""
    if fn not in INVALIDATORS:
        INVALIDATORS.append(fn)


def _fresh(home: Path, owner: str, digest: str) -> dict:
    try:
        plan = make_plan(home, owner, load_selection(home, owner, digest), save=False)
    except PlanError as exc:
        raise PlanError("PLAN_DRIFTED" if exc.code == "NOT_FOUND" else exc.code) from None
    if plan["plan_digest"] != digest:
        raise PlanError("PLAN_DRIFTED")
    return plan


def _template(plan: dict, method: str, reason: str) -> dict:
    counts: dict[str, int] = {}
    for store, items in plan["keys"].items():
        for data_class in _CLASSES.get(store, ()):
            counts[data_class] = counts.get(data_class, 0) + len(items)
    residue = dict(plan["residue_forecast"])
    if plan["receipts"]:
        residue["receipt_commitments"] = len(plan["receipts"])
    return {"stores": sorted(plan["keys"]), "counts": counts, "reason_code": reason,
            "residue": residue, "out_of_reach": plan["out_of_reach"], "presence": method}


def _run(home: Path, owner: str, plan: dict, method: str, reason: str) -> dict:
    from .private_artifact_fs import root_identity
    from .trace_keystore import Keystore
    state = home / "state"
    keystore, identity = Keystore(state, owner), root_identity(state)

    def invalidate():
        for fn in list(INVALIDATORS):
            fn()

    def destroy_keys():
        for store, items in plan["keys"].items():
            keystore.destroy(store, items)

    def remove_files():
        for entry in plan["entries"]:
            remove(state, entry["rel"], expected=identity)

    def verify(scan_set):
        present = [e for e in plan["entries"] if (state / e["rel"]).exists()]
        keys = [e for e in plan["entries"] if keystore.present(e["store"], e["item"])]
        reason_code = "KEY_PRESENT" if keys else ("RESIDUE_FOUND" if present else None)
        return {"ok": reason_code is None, "reason": reason_code,
                "checks": ["keys_absent", "files_absent"]}
    journal = DeletionJournal(state, owner, plan["plan_digest"])
    return apply_journaled(journal, [("invalidate", invalidate), ("destroy_keys", destroy_keys),
                                     ("remove_files", remove_files)], verify,
                           tombstone=_template(plan, method, reason))


def _check_writers(state: Path, plan: dict) -> None:
    """A trace whose run holds its writer lock is busy. The lock file sits in
    the folder being removed, so it is taken and released, not kept: a
    finished operation's trace never gets a new writer."""
    for entry in plan["entries"]:
        if entry["store"] == "S1" and (state / entry["rel"]).is_dir():
            with ExclusiveJourneyLock.acquire(state / entry["rel"] / ".writer.lock", 0):
                pass


def apply_plan(home, owner: str, plan_digest: str, presence_ref, *, sink=None,
               reason: str = "owner_request") -> dict:
    from .trace_presence import STATEMENT, require
    from .trace_witness import record_custody_event
    home = Path(home)
    plan = _fresh(home, owner, plan_digest)
    method = require(home / "state", owner, "delete_apply", plan_digest, presence_ref)
    try:
        with custody_lock(home / "state"):
            _check_writers(home / "state", plan)
            result = _run(home, owner, plan, method, reason)
    except JourneyLockBusy:
        result = {"state": "DELETE_PENDING", "reason": "ITEM_BUSY", "checks": []}
    report = {**result, "plan_digest": plan_digest, "stores": sorted(plan["keys"]),
              "counts": plan["counts"], "out_of_reach": plan["out_of_reach"],
              "remedies": plan["remedies"], "residue": _template(plan, method, reason)["residue"],
              "presence": method, "presence_statement": STATEMENT if method == "none" else ""}
    if result["state"] == "DELETED":
        event = record_custody_event(home, owner, "deletion", {
            "plan_digest": plan_digest, "stores": report["stores"],
            "items": len(plan["entries"]), "reason_code": reason,
            "residue": report["residue"], "out_of_reach": plan["out_of_reach"]}, method, sink=sink)
        report["witness"] = event["witness"]
        drop_selection(home, owner, plan_digest)
    return report
