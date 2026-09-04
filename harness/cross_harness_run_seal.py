"""Seal a finished run into the two documents a reader actually opens.

Every attempt is sealed as it ends. The run-level scorecard is written once, at
the end, which used to mean a run that raised on its way out left a full set of
paid attempts and nothing to read them from. The 2026-09-04 head-to-head lost
its scorecard that way: 35 attempts completed, the source tree had been edited
while they ran, and the drift guard raised before the document was written.

The guard was right about the drift and wrong about what to do with it. Drift is
a fact about the run, so it is stamped on both documents and the caller is still
told, after the evidence is on disk. Discarding a run is not the conservative
choice here. It is the choice that leaves someone retyping numbers off a screen.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from harness.cross_harness_artifacts import write_artifact_index

RUN_SCHEMA = "harness.cross-harness-run-receipt/v1"
SCORECARD_SCHEMA = "harness.cross-harness-task-scorecard/v1"


def write_json(path: Path, value: Any) -> Path:
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                               allow_nan=False) + "\n", encoding="utf-8", newline="")
    return path


def seal_run(run_root: Path, *, run_id: str, phase: str, rows: list[dict[str, Any]],
             before: dict[str, Any], after: dict[str, Any],
             indexed: list[Path]) -> tuple[dict[str, Any], str]:
    """Write run.json and comparison-input.json, and say whether the tree held.

    Returns the run receipt and the tree state. Raising on drift is left to the
    caller so that the raise happens after the documents land rather than
    instead of them.
    """
    run_root = Path(run_root)
    state = "drift" if before != after else "clean"
    run = {"schema": RUN_SCHEMA, "run_id": run_id, "phase": phase, "rows": rows,
           "source_snapshot_before": before, "source_snapshot_after": after,
           "source_tree_state": state}
    comparison = write_json(run_root / "comparison-input.json",
                            {"schema": SCORECARD_SCHEMA, "rows": rows, "source_tree_state": state})
    run_path = write_json(run_root / "run.json", run)
    write_artifact_index(run_root, [*indexed, comparison, run_path])
    return run, state


TREE_STATE_LIMITS = {
    "unsealed": "The run raised before sealing, so nothing ever checked that the "
                "source tree still matched the commit these rows name. The attempts "
                "each verified their own workspace, which is a narrower claim.",
    "drift": "The source tree changed while the run was in flight, so the commit "
             "these rows name does not describe the tree that produced them.",
    "unrecorded": "This scorecard does not say whether the source tree held, so "
                  "the commit these rows name is unchecked.",
}


def scorecard_limitations(paths: Iterable[str | Path]) -> list[str]:
    """What each scorecard admits about the run that produced it.

    A scorecard with no `source_tree_state` predates the field and is left alone.
    Inventing a limitation for it would be as wrong as dropping a real one.
    """
    out: list[str] = []
    for path in paths:
        try:
            state = json.loads(Path(path).read_text(encoding="utf-8")).get("source_tree_state")
        except (OSError, ValueError):
            continue
        limit = TREE_STATE_LIMITS.get(state)
        if limit and limit not in out:
            out.append(limit)
    return out


def scorecard_provenance(paths: Iterable[str | Path], repo_root: Path) -> list[dict[str, Any]]:
    """Name each pooled scorecard so a reader on another machine can check it.

    The absolute path of the machine that ran the report is unverifiable to
    everyone else, and publishing it puts that machine's layout, and whoever's
    account ran it, on a public page. A content hash is the part a reader can
    act on: fetch the scorecard, hash it, compare. The path is kept only when the
    document is inside the repository, where it names the same file for anyone
    who cloned it.
    """
    out: list[dict[str, Any]] = []
    for path in paths:
        resolved = Path(path).resolve()
        entry: dict[str, Any] = {"name": resolved.name, "sha256": None, "repo_path": None}
        try:
            entry["sha256"] = hashlib.sha256(resolved.read_bytes()).hexdigest()
        except OSError:
            pass  # An unreadable scorecard is named without a hash rather than dropped.
        try:
            entry["repo_path"] = resolved.relative_to(Path(repo_root).resolve()).as_posix()
        except ValueError:
            pass  # Outside the repo, so no path means the same thing to a reader.
        out.append(entry)
    return out
