"""self_improve_library.py -- carried-over lessons with provenance, quarantine and rollback.

Harness-squared carries adopted harnesses and lessons from task to task. That
store is also how one bad lesson spreads: a later editor reads it and copies it.
This library makes the spread containable.

  * Provenance. Each lesson names the receipt that admitted it, the task it
    came from, and the lessons the editor was shown when it was written
    (its parents). The journal is hash-chained, so history cannot be edited
    without the chain saying so.
  * Quarantine first. A lesson enters quarantined. Only a lesson whose receipt
    re-verifies as MATCH with decision ADOPT is admitted, and only admitted
    lessons are served to an editor.
  * Cascade. Quarantining a lesson quarantines every lesson descended from it,
    because a lesson written while reading a bad one inherits its premise.
  * Rollback. Adopted harness versions form a lineage. Rolling back restores an
    earlier version and quarantines every lesson introduced after it.

Standard library only.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import self_improve_tree as st
from .evidence_json import canonical_sha256
from .self_improve_receipt import MATCH, verify_edit_receipt

SCHEMA = "flywheel.harness-lesson-library/v1"
GENESIS = "0" * 64
QUARANTINED, ADMITTED = "quarantined", "admitted"


@dataclass
class LessonLibrary:
    lessons: dict[str, dict] = field(default_factory=dict)
    journal: list[dict] = field(default_factory=list)
    versions: list[dict] = field(default_factory=list)

    # -- journal -------------------------------------------------------
    def _log(self, event: str, **fields) -> dict:
        prev = self.journal[-1]["hash"] if self.journal else GENESIS
        row = {"seq": len(self.journal), "event": event, "prev": prev, **fields}
        row["hash"] = canonical_sha256(row)
        self.journal.append(row)
        return row

    def status(self, lesson_id: str) -> str:
        state = ""
        for row in self.journal:
            if row.get("lesson_id") == lesson_id:
                state = {"add": QUARANTINED, "admit": ADMITTED,
                         "quarantine": QUARANTINED}.get(row["event"], state)
        if not state:
            raise KeyError(lesson_id)
        return state

    # -- lessons -------------------------------------------------------
    def add(self, *, cue: str, lesson: str, components: list[str], source_task: str,
            receipt_seal: str, parents: list[str] | None = None) -> str:
        """Record a lesson, quarantined, and return its id."""
        parents = sorted(set(parents or []))
        unknown = [p for p in parents if p not in self.lessons]
        if unknown:
            raise KeyError(f"unknown parent lessons: {unknown}")
        body = {"cue": cue, "lesson": lesson, "components": sorted(components),
                "source_task": source_task, "receipt_seal": receipt_seal, "parents": parents}
        lesson_id = canonical_sha256(body)
        if lesson_id not in self.lessons:
            self.lessons[lesson_id] = body
            self._log("add", lesson_id=lesson_id)
        return lesson_id

    def admit(self, lesson_id: str, receipt: dict) -> bool:
        """Admit only on a receipt that re-verifies and decided ADOPT."""
        body = self.lessons[lesson_id]
        if receipt.get("seal_sha256") != body["receipt_seal"]:
            raise ValueError("receipt is not the one this lesson names")
        check = verify_edit_receipt(receipt)
        if check["verdict"] != MATCH or receipt.get("decision") != "ADOPT":
            self._log("refuse", lesson_id=lesson_id, reason=check["detail"][:200])
            return False
        if any(self.status(p) != ADMITTED for p in body["parents"]):
            self._log("refuse", lesson_id=lesson_id, reason="a parent lesson is not admitted")
            return False
        self._log("admit", lesson_id=lesson_id)
        return True

    def descendants(self, lesson_id: str) -> list[str]:
        out, frontier = set(), {lesson_id}
        while frontier:
            nxt = {lid for lid, b in self.lessons.items()
                   if set(b["parents"]) & frontier and lid not in out}
            out |= nxt
            frontier = nxt
        return sorted(out)

    def quarantine(self, lesson_id: str, reason: str) -> list[str]:
        """Quarantine a lesson and every descendant; returns the ids touched."""
        touched = [lesson_id] + self.descendants(lesson_id)
        for lid in touched:
            if self.status(lid) != QUARANTINED:
                self._log("quarantine", lesson_id=lid, reason=reason[:200],
                          root=lesson_id)
        return touched

    def served(self) -> list[dict]:
        """The lessons an editor may read: admitted ones only, oldest first."""
        return [{"id": lid, **b} for lid, b in self.lessons.items()
                if self.status(lid) == ADMITTED]

    # -- harness lineage -----------------------------------------------
    def commit_version(self, tree: st.Tree, *, receipt_seal: str,
                       lessons: list[str] | None = None) -> int:
        version = len(self.versions)
        self.versions.append({"version": version, "tree": dict(tree),
                              "digest": st.digest(tree), "receipt_seal": receipt_seal,
                              "lessons": sorted(lessons or []), "active": True})
        self._log("commit", version=version, digest=st.digest(tree))
        return version

    def incumbent(self) -> st.Tree:
        active = [v for v in self.versions if v["active"]]
        if not active:
            raise LookupError("no committed harness version")
        return dict(active[-1]["tree"])

    def rollback(self, to_version: int, reason: str) -> list[str]:
        """Restore a version; deactivate later ones and quarantine their lessons."""
        if not 0 <= to_version < len(self.versions):
            raise IndexError(to_version)
        touched: list[str] = []
        for v in self.versions[to_version + 1:]:
            if v["active"]:
                v["active"] = False
                for lid in v["lessons"]:
                    touched += self.quarantine(lid, f"rollback: {reason}")
        self._log("rollback", version=to_version, reason=reason[:200])
        return sorted(set(touched))

    # -- persistence ---------------------------------------------------
    def verify_chain(self) -> bool:
        prev = GENESIS
        for row in self.journal:
            body = {k: v for k, v in row.items() if k != "hash"}
            if row["prev"] != prev or canonical_sha256(body) != row["hash"]:
                return False
            prev = row["hash"]
        return True

    def save(self, path: Path) -> Path:
        doc = {"schema": SCHEMA, "lessons": self.lessons, "journal": self.journal,
               "versions": self.versions}
        Path(path).write_text(json.dumps(doc, indent=1, sort_keys=True), encoding="utf-8")
        return Path(path)

    @classmethod
    def load(cls, path: Path) -> "LessonLibrary":
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        if doc.get("schema") != SCHEMA:
            raise ValueError("not a harness lesson library")
        lib = cls(doc["lessons"], doc["journal"], doc["versions"])
        if not lib.verify_chain():
            raise ValueError("library journal does not re-verify")
        return lib
