"""Preregistration: write PREREG and its sha256 before any run, and check both before scoring.

Two anchors, either is enough to run, both are checked when present:
  * the sha256 declared in the spec (prereg.sha256), for a PREREG frozen elsewhere, like runs2/;
  * prereg.lock.json, written by `studyrun prereg`, which also freezes the plan (analysis,
    controls, verdict rules, seed) by plan_sha256.
A sidecar PREREG.sha256 in `sha256sum` format is written beside the PREREG and checked when it exists.
"""
import datetime as dt
import json
from pathlib import Path

from . import LOCK_SCHEMA, anchor
from .hashing import FORM, LEGACY_FORM, sha256_file
from .spec import plan_sha256


class PreregError(RuntimeError):
    pass


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _sidecar(prereg_path):
    p = Path(prereg_path)
    return p.with_name(p.stem + ".sha256")


def write(spec):
    """Write PREREG (from spec prereg.text when the file is absent), its sidecar and the lock.

    A new lock also requires a truth-anchored measure beside any update-size metric (anchor.py,
    F95 MT3). The check runs before anything is written; existing locks are not re-checked.
    """
    unanchored = anchor.problems(spec)
    if unanchored:
        raise PreregError("refusing to lock: " + "; ".join(unanchored))
    p = Path(spec["_prereg_path"])
    text = spec["prereg"].get("text")
    if not p.exists():
        if not text:
            raise PreregError(f"{p} does not exist and the spec carries no prereg.text")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
    elif text and p.read_text(encoding="utf-8") != text:
        raise PreregError(f"{p} exists with other content; a preregistration is never rewritten")
    digest = sha256_file(p)
    declared = spec["prereg"].get("sha256")
    if declared and declared != digest:
        raise PreregError(f"{p} hashes {digest}, the spec declares {declared}")
    side = _sidecar(p)
    if not side.exists():
        side.write_text(f"{digest} *{p.name}\n", encoding="utf-8", newline="\n")
    lock = {"schema": LOCK_SCHEMA, "study": spec["id"], "prereg_path": str(p), "prereg_sha256": digest,
            "plan_sha256": plan_sha256(spec), "canonical_form": FORM, "written_at": _now()}
    lp = Path(spec["_lock_path"])
    if lp.exists():
        raise PreregError(f"{lp} exists; the lock is written once")
    lp.parent.mkdir(parents=True, exist_ok=True)
    lp.write_text(json.dumps(lock, indent=1) + "\n", encoding="utf-8", newline="\n")
    return lock


def check(spec):
    """Return (record, problems). No problems means the PREREG and plan are as frozen."""
    p = Path(spec["_prereg_path"])
    if not p.is_file():
        return {}, [f"PREREG missing: {p}"]
    digest = sha256_file(p)
    rec = {"path": str(p), "sha256": digest, "anchors": [], "plan_sha256": plan_sha256(spec)}
    bad = []
    declared = spec["prereg"].get("sha256")
    if declared:
        rec["anchors"].append("spec")
        if declared != digest:
            bad.append(f"PREREG hashes {digest}, spec declares {declared}")
    side = _sidecar(p)
    if side.is_file():
        rec["anchors"].append("sidecar")
        if side.read_text(encoding="utf-8").split()[0] != digest:
            bad.append(f"PREREG hashes {digest}, {side.name} says otherwise")
    lp = Path(spec["_lock_path"])
    if lp.is_file():
        rec["anchors"].append("lock")
        lock = json.loads(lp.read_text(encoding="utf-8"))
        if lock.get("prereg_sha256") != digest:
            bad.append("PREREG changed since the lock was written")
        form = lock.get("canonical_form", LEGACY_FORM)
        if lock.get("plan_sha256") != plan_sha256(spec, form):
            bad.append("plan (analysis, controls, verdicts, seed) changed since the lock was written")
        rec["locked_at"] = lock.get("written_at")
    else:
        rec["plan_frozen"] = False
    if not declared and not lp.is_file():
        bad.append("no anchor: declare prereg.sha256 in the spec or run `studyrun prereg` first")
    return rec, bad
