"""The deletion journal and its encrypted scan set (7.10, SP-17, I14).

A deletion writes its intent before it acts:
`state/trace-deletions/v1/owners/<owner>/journal/<plan>.journal` holds the
step names, the steps done and the tombstone template (metadata only), and
`<plan>.scan` holds the content of the plaintext rows and files to be
deleted, so a deletion interrupted between apply and verify can still check
for residue. Both are encrypted under a per-deletion key in the keystore's
`deletions` shard. Each step is marked done durably after it runs, so a rerun
resumes at the first step not done. Only a verified deletion writes a
tombstone; writing it destroys the scan-set key and removes the journal. With
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
        self.dir.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        with open(temporary, "wb") as stream:
            stream.write(self.cipher.seal(name, payload))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)

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

    def begin(self, steps, scan_set, template: dict) -> None:
        doc = {"schema": "flywheel.trace-deletion-journal/v1", "plan_digest": self.plan,
               "steps": list(steps), "done": [], "template": template,
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
            entry = TombstoneLedger(self.state_root, self.owner_ref).append(**fields)
            self.cipher.keystore.destroy(STORE, [self.plan])
            for path in (self.scan_path, self.path):
                path.unlink(missing_ok=True)
        return entry


def _tombstone_fields(journal: DeletionJournal, doc: dict, verdict: dict) -> dict:
    template = {"stores": [], "counts": {}, "residual": {}, "residue": {},
                "out_of_reach": {}, "presence": "none", "reason_code": "owner_request",
                **doc.get("template", {})}
    return {**template, "plan_digest": journal.plan, "started_at": doc["started_at"],
            "checks": verdict.get("checks", []),
            "residual": verdict.get("residual", template["residual"])}


def apply_journaled(journal: DeletionJournal, steps, verify, *, scan_set=None,
                    tombstone=None) -> dict:
    """Run `steps` (name, callable) under the journal, then `verify(scan_set)`.
    Faults propagate and leave the journal for a rerun to resume."""
    if not journal.exists():
        journal.begin([name for name, _ in steps], scan_set, dict(tombstone or {}))
    done = journal.done_steps()
    for name, run in steps:
        if name not in done:
            run()
            journal.mark(name)
    verdict = verify(journal.scan_set())
    if not verdict.get("ok"):
        return {"state": "DELETE_PENDING", "reason": verdict.get("reason", "RESIDUE_FOUND"),
                "checks": verdict.get("checks", [])}
    entry = journal.finish(_tombstone_fields(journal, journal.state(), verdict))
    return {"state": "DELETED", "tombstone_ref": entry["tombstone_ref"],
            "checks": verdict.get("checks", [])}
