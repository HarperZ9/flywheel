"""The deletion journal and its encrypted scan set (7.10, SP-17, I14).

A deletion writes its intent before it acts:
`state/trace-deletions/v1/owners/<owner>/journal/<plan>.journal` holds the
step names, the steps done and the tombstone template (metadata only), and
`<plan>.scan` holds the content of the plaintext rows and files to be
deleted, so a deletion interrupted between apply and verify can still check
for residue. Both are encrypted under a per-deletion key in the keystore's
`deletions` shard. Each step is marked done durably after it runs, so a rerun
resumes at the first step not done. Only a verified deletion writes a
tombstone. Finishing writes the tombstone (once: a tombstone for the plan
already in the ledger is reused), removes the scan set and journal and syncs
the folder, and only then destroys the scan-set key, so a crash at any gap
leaves either a readable journal or a tombstone that marks the plan done. With
no OS key store the scan set is not written and verification falls back to
structural checks, which the tombstone names.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path

from .evidence_json import canonical_bytes
from .trace_custody_lock import custody_lock
from .trace_enc_write import ItemCipher
from .trace_tombstones import TombstoneLedger

STORE = "deletions"
_log = logging.getLogger(__name__)


def _dir(state_root, owner_ref: str) -> Path:
    return Path(state_root) / "trace-deletions" / "v1" / "owners" / owner_ref / "journal"


def pending(state_root, owner_ref: str) -> list[str]:
    directory = _dir(state_root, owner_ref)
    return sorted(p.stem for p in directory.glob("*.journal")) if directory.is_dir() else []


class DeletionJournal:
    def __init__(self, state_root, owner_ref: str, plan_digest: str, *, provider=None) -> None:
        self.state_root, self.owner_ref, self.plan = Path(state_root), owner_ref, plan_digest
        self.dir = _dir(state_root, owner_ref)
        self.path = self.dir / f"{plan_digest}.journal"
        self.scan_path = self.dir / f"{plan_digest}.scan"
        self.cipher = ItemCipher(self.state_root, owner_ref, STORE, plan_digest, provider=provider)

    def _write(self, path: Path, name: str, payload: bytes) -> None:
        from . import trace_durable
        trace_durable.write_durable(path, self.cipher.seal(name, payload))

    def _read(self, path: Path, name: str) -> bytes | None:
        try:
            blob = path.read_bytes()
        except FileNotFoundError:
            return None
        self.cipher.prefix.reset()
        return self.cipher.open(name, blob)

    def exists(self) -> bool:
        return self.path.exists()

    def state(self) -> dict:
        raw = self._read(self.path, "journal")
        return json.loads(raw) if raw else {}

    def begin(self, steps, scan_set, template: dict, extra=None) -> None:
        doc = {"schema": "flywheel.trace-deletion-journal/v1", "plan_digest": self.plan,
               "steps": list(steps), "done": [], "template": template, **(extra or {}),
               "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")
               .replace("+00:00", "Z")}
        if scan_set is not None and self.cipher.encrypting:
            self._write(self.scan_path, "scan", canonical_bytes(list(scan_set)))
        self._write(self.path, "journal", canonical_bytes(doc))

    def mark(self, step: str) -> None:
        doc = self.state()
        if step not in doc["done"]:
            doc["done"].append(step)
        self._write(self.path, "journal", canonical_bytes(doc))

    def done_steps(self) -> set[str]:
        return set(self.state().get("done", []))

    def scan_set(self) -> list[str] | None:
        try:
            raw = self._read(self.scan_path, "scan")
        except Exception as exc:  # unreadable on resume: the caller runs structural checks
            _log.warning("deletion scan set unreadable (%s)", type(exc).__name__)
            return None
        return json.loads(raw) if raw else None

    def finish(self, fields: dict) -> dict:
        with custody_lock(self.state_root):
            entry = tombstone_for(self.state_root, self.owner_ref, self.plan)
            if entry is None:
                entry = TombstoneLedger(self.state_root, self.owner_ref).append(**fields)
            _remove_files(self)
            self.cipher.keystore.destroy(STORE, [self.plan])
        return entry


def _remove_files(journal: DeletionJournal) -> None:
    for path in (journal.scan_path, journal.path):
        path.unlink(missing_ok=True)
    if os.name != "nt" and journal.dir.is_dir():
        descriptor = os.open(journal.dir, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def tombstone_for(state_root, owner_ref: str, plan_digest: str) -> dict | None:
    for entry in TombstoneLedger(state_root, owner_ref).entries():
        if entry.get("plan_digest") == plan_digest:
            return entry
    return None


def finished(state_root, owner_ref: str, plan_digest: str) -> dict | None:
    """A plan whose tombstone is written is done: clear any journal files and
    scan-set key a crash left, and report it; None when it is not done."""
    entry = tombstone_for(state_root, owner_ref, plan_digest)
    if entry is None:
        return None
    journal = DeletionJournal(state_root, owner_ref, plan_digest)
    with custody_lock(journal.state_root):
        _remove_files(journal)
        journal.cipher.keystore.destroy(STORE, [plan_digest])
    return {"state": "DELETED", "tombstone_ref": entry["tombstone_ref"],
            "checks": entry.get("checks", [])}


def resume_or_done(journal: DeletionJournal, rerun) -> dict:
    return finished(journal.state_root, journal.owner_ref, journal.plan) or rerun()


def _tombstone_fields(journal: DeletionJournal, doc: dict, verdict: dict) -> dict:
    template = {"stores": [], "counts": {}, "residual": {}, "residue": {},
                "out_of_reach": {}, "presence": "none", "reason_code": "owner_request",
                **doc.get("template", {})}
    return {**template, "plan_digest": journal.plan, "started_at": doc["started_at"],
            "checks": verdict.get("checks", []),
            "residual": verdict.get("residual", template["residual"])}


def apply_journaled(journal: DeletionJournal, steps, verify, *, scan_set=None,
                    tombstone=None, extra=None, lock=None) -> dict:
    """Run `steps` (name, callable) under the journal, then `verify(scan_set)`.
    Faults propagate and leave the journal for a rerun to resume. With `lock`
    (a context-manager factory) the steps and the finish run under it and the
    verification does not, so a long residual scan never holds up captures."""
    import contextlib
    lock = lock or contextlib.nullcontext
    with lock():
        done = finished(journal.state_root, journal.owner_ref, journal.plan)
        if done:
            return done
        if not journal.exists():
            journal.begin([name for name, _ in steps], scan_set, dict(tombstone or {}), extra)
        done = journal.done_steps()
        for name, run in steps:
            if name not in done:
                run()
                journal.mark(name)
    verdict = verify(journal.scan_set())
    if not verdict.get("ok"):
        return {"state": "DELETE_PENDING", "reason": verdict.get("reason", "RESIDUE_FOUND"),
                "checks": verdict.get("checks", [])}
    with lock():
        entry = journal.finish(_tombstone_fields(journal, journal.state(), verdict))
    return {"state": "DELETED", "tombstone_ref": entry["tombstone_ref"],
            "checks": verdict.get("checks", [])}
