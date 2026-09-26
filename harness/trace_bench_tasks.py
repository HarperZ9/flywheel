"""Bench tasks from gateway traces, in private custody (7.8 stage A, FW-12a).

A gateway trace's `request` record holds the submitted operation and the
execution binding; the goal is materialized from them the way the run did
it, and the gate is the operation's `test_cmd`. The `result` record's
`tests_pass` gives the prior verdict (PASS, FAIL, or UNKNOWN without one).
A run without a gate command is skipped and counted, never faked.

Each task (schema `flywheel.trace-task/v2`) is sealed under
`state/trace-bench/v1/owners/<owner>/tasks/<task_ref>.enc` (store BT) with
lineage to its trace and `content_trust` (untrusted when the goal carries
selected source context). A plaintext index holds only task ref, trace ref,
verdict and reproducibility class. A task is REPRODUCIBLE when the run
recorded a git identity with no tracked change and no untracked file at
start and the commit is still in the repository; otherwise UNREPRODUCIBLE
with a reason (NOT_A_GIT_TREE, which includes runs from before git
identities were recorded, DIRTY_AT_START or COMMIT_MISSING). Only
reproducible tasks can count as regressions.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import secrets

from .evidence_json import canonical_bytes

_log = logging.getLogger(__name__)
STORE = "BT"
SCHEMA = "flywheel.trace-task/v2"


class _SealedIndex:
    """Sealed items under one folder of the bench store, with a plaintext
    index holding refs, verdicts and classes only."""
    FOLDER, KEY, FIELDS, NAME = "", "", (), ""

    def __init__(self, home, owner: str) -> None:
        from .trace_keystore import Keystore
        self.home, self.owner = Path(home), owner
        self.state = self.home / "state"
        self.base = self.state / "trace-bench" / "v1" / "owners" / owner / self.FOLDER
        self.keystore = Keystore(self.state, owner)

    def _cipher(self, ref: str):
        from .trace_enc_write import ItemCipher
        return ItemCipher(self.state, self.owner, STORE, ref, keystore=self.keystore)

    def index(self) -> list[dict]:
        path = self.base / "index.jsonl"
        if not path.is_file():
            return []
        return [json.loads(line) for line in path.read_bytes().splitlines() if line.strip()]

    def _write_index(self, rows: list[dict]) -> None:
        self.base.mkdir(parents=True, exist_ok=True)
        temporary = self.base / ".index.jsonl.tmp"
        temporary.write_bytes(b"".join(canonical_bytes(r) + b"\n" for r in rows))
        os.replace(temporary, self.base / "index.jsonl")

    def read(self, ref: str) -> dict:
        raw = (self.base / f"{ref}.enc").read_bytes()
        return json.loads(self._cipher(ref).open(self.NAME, raw))

    def add(self, doc: dict) -> None:
        from .trace_custody_lock import custody_lock
        ref = doc[self.KEY]
        with custody_lock(self.state):
            self.base.mkdir(parents=True, exist_ok=True)
            (self.base / f"{ref}.enc").write_bytes(self._cipher(ref).seal(self.NAME,
                                                                        canonical_bytes(doc)))
            self._write_index(self.index() + [{k: doc[k] for k in self.FIELDS}])

    def drop(self, refs) -> None:
        from .trace_custody_lock import custody_lock
        gone = set(refs)
        with custody_lock(self.state):
            self._write_index([r for r in self.index() if r[self.KEY] not in gone])

    def entries(self, refs) -> list[dict]:
        return [{"store": STORE, "item": ref,
                 "rel": (self.base / f"{ref}.enc").relative_to(self.state).as_posix()}
                for ref in refs]


class BenchTasks(_SealedIndex):
    FOLDER, KEY, NAME = "tasks", "task_ref", "task"
    FIELDS = ("task_ref", "trace_ref", "prior_verdict", "class", "reason")


class ReplayResults(_SealedIndex):
    """Replay results (FW-12b1), with lineage to their task."""
    FOLDER, KEY, NAME = "results", "result_ref", "result"
    FIELDS = ("result_ref", "task_ref", "endpoint", "verdict")


def _facts(records: list[dict]) -> dict | None:
    """Goal, gate, verdict, binding and git identity of one traced run."""
    from .gateway_operation import materialize_agent_attachment
    from .source_context_worker import materialize_goal
    request = next((r["payload"] for r in records if r["kind"] == "request"), None)
    if not request or type(request.get("operation")) is not dict:
        return None
    execution = materialize_agent_attachment(request["operation"])
    context = request.get("source_context")
    result = next((r["payload"] for r in records if r["kind"] == "result"), {})
    passed = result.get("tests_pass")
    git = next((json.loads(r["payload"]["content"]) for r in records if r["kind"] == "ledger"
                and r["payload"].get("kind") == "workspace_git"), None)
    return {"goal": materialize_goal(execution["goal"], context) if context else
            execution["goal"], "gate_cmd": execution.get("test_cmd"),
            "prior_verdict": "UNKNOWN" if passed is None else "PASS" if passed else "FAIL",
            "binding": request.get("execution_binding") or {}, "git": git,
            "content_trust": "untrusted" if context else "owner"}


def classify(git: dict | None, workspace: str | None) -> tuple[str, str | None]:
    from .workspace_git_identity import commit_exists
    if not git:
        return "UNREPRODUCIBLE", "NOT_A_GIT_TREE"
    if not git.get("clean"):
        return "UNREPRODUCIBLE", "DIRTY_AT_START"
    if not workspace or not commit_exists(workspace, git.get("head")):
        return "UNREPRODUCIBLE", "COMMIT_MISSING"
    return "REPRODUCIBLE", None


def _task(trace_ref: str, facts: dict) -> dict:
    binding = facts["binding"]
    workspace = (binding.get("workspace") or {}).get("root")
    cls, reason = classify(facts["git"], workspace)
    return {"schema": SCHEMA, "task_ref": "tsk_" + secrets.token_hex(16),
            "trace_ref": trace_ref, "lineage": {"source_trace_ref": trace_ref},
            "goal": facts["goal"], "gate_cmd": facts["gate_cmd"],
            "prior_verdict": facts["prior_verdict"],
            "endpoint": (binding.get("endpoint") or {}).get("name"),
            "model": (binding.get("model") or {}).get("model_id"),
            "capabilities": binding.get("capabilities") or {}, "workspace": workspace,
            "git": facts["git"], "content_trust": facts["content_trust"], "class": cls,
            "reason": reason}


def build_tasks(home, owner: str) -> dict:
    """One task per gateway trace with a gate; counts per class and skip."""
    from .source_context_error import SourceContextError
    from .trace_export_stores import gateway_traces
    store = BenchTasks(home, owner)
    have = {row["trace_ref"] for row in store.index()}
    report = {"tasks": 0, "skipped": {}, "classes": {}}
    for trace_ref, records in gateway_traces(Path(home), owner):
        if trace_ref in have:
            continue
        try:
            facts = _facts(records)
        except (ValueError, KeyError, TypeError, SourceContextError) as exc:
            _log.warning("trace %s: request not readable as a task (%s)", trace_ref[:12],
                         type(exc).__name__)
            report["skipped"]["UNREADABLE_REQUEST"] = report["skipped"].get(
                "UNREADABLE_REQUEST", 0) + 1
            continue
        if not facts or not facts["gate_cmd"]:
            report["skipped"]["NO_GATE"] = report["skipped"].get("NO_GATE", 0) + 1
            continue
        task = _task(trace_ref, facts)
        store.add(task)
        report["tasks"] += 1
        report["classes"][task["class"]] = report["classes"].get(task["class"], 0) + 1
    return report


def task_entries(home, owner: str, trace_ref: str) -> list[dict]:
    """Deletion closure: the tasks derived from a trace and their results."""
    tasks, results = BenchTasks(home, owner), ReplayResults(home, owner)
    mine = [r["task_ref"] for r in tasks.index() if r["trace_ref"] == trace_ref]
    return tasks.entries(mine) + results.entries(
        [r["result_ref"] for r in results.index() if r["task_ref"] in mine])


def drop_rows(home, owner: str, entries: list[dict]) -> None:
    refs = [e["item"] for e in entries if e["store"] == STORE]
    if refs:
        for store in (BenchTasks(home, owner), ReplayResults(home, owner)):
            store.drop(refs)


def rows_present(home, owner: str, entries: list[dict]) -> bool:
    refs = {e["item"] for e in entries if e["store"] == STORE}
    return bool(refs) and any(r[s.KEY] in refs for s in (BenchTasks(home, owner),
                                                         ReplayResults(home, owner))
                              for r in s.index())


def _owners(home) -> list[str]:
    base = Path(home) / "state" / "trace-bench" / "v1" / "owners"
    return sorted(p.name for p in base.iterdir() if p.is_dir()) if base.is_dir() else []


def export_records(home) -> list[dict]:
    out = []
    for owner in _owners(home):
        for store in (BenchTasks(home, owner), ReplayResults(home, owner)):
            out += [store.read(row[store.KEY]) for row in store.index()]
    return out


def delete_all(home) -> dict:
    from .trace_meta_adapters import remove_tree
    removed = 0
    for owner in _owners(home):
        for store in (BenchTasks(home, owner), ReplayResults(home, owner)):
            store.keystore.destroy(STORE, [row[store.KEY] for row in store.index()])
        removed += remove_tree(store.base.parent)
    return {"removed": removed}
