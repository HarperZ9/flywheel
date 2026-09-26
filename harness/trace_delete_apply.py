"""Apply a deletion plan (7.10, I4, I14, I17).

Apply recomputes the plan from the saved selection and refuses one whose
digest differs (PLAN_DRIFTED), unless a journal for that digest exists, in
which case it resumes the plan the journal holds. It requires presence bound
to the digest and refuses a trace whose run holds its writer lock
(ITEM_BUSY). Under the custody lock and the journal: running stores drop
cached copies, deleted imports join the exclusion list, item keys are
destroyed, encrypted files are removed by handle, store.db rows go through the checked scrub (DB_BUSY stops the step
for a later rerun), and plaintext items are removed or rewritten away. Then
verification: files, rows and keys absent, and no window of deleted text in
the plaintext stores' files. Only then a tombstone, a ledger entry and a
witness event. The report names copies outside reach, residue, and every
store no deletion covers yet.
"""
from __future__ import annotations

from pathlib import Path

from .journey_lock import ExclusiveJourneyLock, JourneyLockBusy
from .private_artifact_remove import remove
from .trace_custody_lock import custody_lock
from .trace_delete_adapters_import import drop_index_rows, exclude, indexed
from .trace_delete_apply_plain import ScrubPending, remove_plain, scrub_store, verify_plain
from .trace_delete_journal import DeletionJournal, apply_journaled
from .trace_delete_plan import (ENCRYPTED, PlanError, drop_selection, load_selection,
                                make_plan, roots_for)

INVALIDATORS: list = []
_CLASSES = {"S1": ("C1", "C2", "C4", "C5"), "CT": ("C1", "C4", "C5"), "S8b": ("C1", "C4"),
            "S7": ("C4", "C5"), "S9": ("C1",), "S10": ("C1", "C2"), "S11": ("C1", "C2"),
            "S2": ("C1", "C4", "C5"), "IM": ("C1", "C2", "C4", "C5")}


def register_invalidator(fn) -> None:
    """A running store registers how to drop its cached copies (SP-15)."""
    if fn not in INVALIDATORS:
        INVALIDATORS.append(fn)


def _plan_for(home: Path, owner: str, digest: str, roots: dict) -> dict:
    journal = DeletionJournal(home / "state", owner, digest)
    if journal.exists() and journal.state().get("plan"):
        return journal.state()["plan"]
    try:
        plan = make_plan(home, owner, load_selection(home, owner, digest), save=False,
                         roots=roots)
    except PlanError as exc:
        raise PlanError("PLAN_DRIFTED" if exc.code == "NOT_FOUND" else exc.code) from None
    if plan["plan_digest"] != digest:
        raise PlanError("PLAN_DRIFTED")
    return plan


def _template(plan: dict, method: str, reason: str) -> dict:
    counts: dict[str, int] = {}
    for entry in plan["entries"]:
        for data_class in _CLASSES.get(entry["store"], ()):
            counts[data_class] = counts.get(data_class, 0) + 1
    return {"stores": sorted(plan["counts"]), "counts": counts, "reason_code": reason,
            "residue": dict(plan["residue_forecast"]), "out_of_reach": plan["out_of_reach"],
            "presence": method}


def _steps(home: Path, owner: str, plan: dict, roots: dict, reason: str) -> list:
    from .private_artifact_fs import root_identity
    from .trace_keystore import Keystore
    state, keystore = home / "state", Keystore(home / "state", owner)
    encrypted = [e for e in plan["entries"] if e["store"] in ENCRYPTED]
    plain = [e for e in plan["entries"] if e["store"] not in ENCRYPTED]

    def invalidate():
        for fn in list(INVALIDATORS):
            fn()

    def destroy_keys():
        for store, items in plan["keys"].items():
            keystore.destroy(store, items)

    def remove_files():
        identity = root_identity(state)
        for entry in encrypted:
            remove(state, entry["rel"], expected=identity)
    return [("invalidate", invalidate),
            ("exclude_imports", lambda: exclude(home, owner, encrypted)),
            ("destroy_keys", destroy_keys), ("remove_files", remove_files),
            ("drop_import_rows", lambda: drop_index_rows(home, owner, encrypted)),
            ("scrub_store_db", lambda: scrub_store(
                home, plain, reason)), ("remove_plain", lambda: remove_plain(roots, plain))]


def _verifier(home: Path, owner: str, plan: dict, roots: dict):
    from .trace_keystore import Keystore
    state, keystore = home / "state", Keystore(home / "state", owner)
    encrypted = [e for e in plan["entries"] if e["store"] in ENCRYPTED]
    plain = [e for e in plan["entries"] if e["store"] not in ENCRYPTED]

    def verify(scan_set):
        if any(keystore.present(e["store"], e["item"]) for e in encrypted):
            return {"ok": False, "reason": "KEY_PRESENT", "checks": ["keys_absent"]}
        if any((state / e["rel"]).exists() for e in encrypted) or indexed(home, owner, encrypted):
            return {"ok": False, "reason": "RESIDUE_FOUND", "checks": ["files_absent"]}
        result = verify_plain(home, roots, plain, scan_set)
        return {**result, "checks": ["keys_absent", "files_absent", *result["checks"]]}
    return verify


def _check_writers(state: Path, plan: dict) -> None:
    """A trace whose run holds its writer lock is busy. The lock file sits in
    the folder being removed, so it is taken and released, not kept: a
    finished operation's trace never gets a new writer."""
    for entry in plan["entries"]:
        if entry["store"] == "S1" and (state / entry["rel"]).is_dir():
            with ExclusiveJourneyLock.acquire(state / entry["rel"] / ".writer.lock", 0):
                pass


def _execute(home: Path, owner: str, plan: dict, roots: dict, method: str, reason: str) -> dict:
    from .trace_delete_adapters_plain import item_texts
    state = home / "state"
    journal = DeletionJournal(state, owner, plan["plan_digest"])
    scan_set = None if journal.exists() else item_texts(
        home, roots, [e for e in plan["entries"] if e["store"] not in ENCRYPTED])
    try:
        with custody_lock(state):
            _check_writers(state, plan)
            return apply_journaled(journal, _steps(home, owner, plan, roots, reason),
                                   _verifier(home, owner, plan, roots), scan_set=scan_set,
                                   tombstone=_template(plan, method, reason),
                                   extra={"plan": plan})
    except JourneyLockBusy:
        return {"state": "DELETE_PENDING", "reason": "ITEM_BUSY", "checks": []}
    except ScrubPending as pending:
        return {"state": "DELETE_PENDING", "reason": pending.reason, "checks": []}


def apply_plan(home, owner: str, plan_digest: str, presence_ref, *, sink=None,
               reason: str = "owner_request") -> dict:
    """Run a saved plan after presence bound to its digest."""
    from .trace_presence import require
    home = Path(home)
    _plan_for(home, owner, plan_digest, roots_for(home))  # drift is refused before presence
    method = require(home / "state", owner, "delete_apply", plan_digest, presence_ref)
    return apply_authorized(home, owner, plan_digest, method, reason=reason, sink=sink)


def apply_authorized(home, owner: str, plan_digest: str, method: str, *, sink=None,
                     reason: str = "owner_request", record: bool = True) -> dict:
    """Run a saved plan whose authority the caller established: presence for
    a manual delete, the adopted policy for retention (7.4). With `record`
    false the caller writes the one ledger entry and witness event itself."""
    from .trace_presence import STATEMENT
    from .trace_witness import record_custody_event
    home = Path(home)
    roots = roots_for(home)
    plan = _plan_for(home, owner, plan_digest, roots)
    result = _execute(home, owner, plan, roots, method, reason)
    report = {**result, "plan_digest": plan_digest, "stores": sorted(plan["counts"]),
              "counts": plan["counts"], "out_of_reach": plan["out_of_reach"],
              "remedies": plan["remedies"], "residue": dict(plan["residue_forecast"]),
              "not_covered": plan["not_covered"], "notes": plan["notes"],
              "items": len(plan["entries"]),
              "presence": method, "presence_statement": STATEMENT if method == "none" else ""}
    if result["state"] == "DELETED":
        if record:
            event = record_custody_event(home, owner, "deletion", {
                "plan_digest": plan_digest, "stores": report["stores"],
                "items": len(plan["entries"]), "reason_code": reason,
                "residue": report["residue"], "out_of_reach": plan["out_of_reach"]}, method,
                sink=sink)
            report["witness"] = event["witness"]
        drop_selection(home, owner, plan_digest)
    return report
