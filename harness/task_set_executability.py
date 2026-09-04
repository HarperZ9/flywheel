"""What fraction of a task set can actually run, and what fraction can be scored.

The 2026-09-03 head-to-head ran seventy attempts and scored two of them. The
receipts said `required input invalid`, which reads like fourteen bad tasks and
was in fact one contract seam between the manifest and the workspace builder.
Nothing in the repository would have caught that before a provider was called
and billed, because the only check on a task set was the manifest build, and the
manifest build hashes inputs without ever trying to seal a workspace.

This module answers two questions about a task set, separately, before any run:

  provisionable  every declared input resolves, so the attempt reaches a provider
  scorable       a registered checker and its fixture exist, so a result is readable

They are not the same question and the difference is the point. A task can be
provisionable and still produce nothing measurable, which is the state ten of
the fourteen tasks in agentic-task-set-v1 are in. One number for both would hide
that.

The gate reads the repository and writes nothing to it.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from harness.cross_harness_input_refs import classify_reference
from harness.cross_harness_manifest import PILOT_TASKS
from harness.cross_harness_oracles import _CHECKERS

SCHEMA = "flywheel.task_set_executability/v1"
VERDICTS = ("TASK_SET_MEASURABLE", "TASK_SET_PARTIAL", "TASK_SET_BLOCKED")
_UNPROVISIONABLE = ("input_missing", "input_reference_invalid", "input_escapes_root")
_UNSCORABLE = ("no_oracle", "checker_", "fixture_missing", "pilot_typed_input")


def _input_state(root: Path, reference: Any) -> tuple[str, str]:
    """Classify one declared input into (state, detail).

    States are `in_tree` for a file the workspace can seal, `typed` for material
    declared and deliberately not provisioned, or a blocker code.
    """
    try:
        scheme, payload = classify_reference(reference)
    except ValueError as exc:
        return "input_reference_invalid", str(exc)
    if scheme != "repo_relative":
        return "typed", f"{scheme}://{payload}"
    relative = Path(payload)
    if relative.is_absolute() or relative.drive or ".." in relative.parts:
        return "input_escapes_root", str(reference)
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root):
        return "input_escapes_root", str(reference)
    if not resolved.is_file():
        return "input_missing", str(reference)
    return "in_tree", payload


def classify_task(root: Path, task: dict[str, Any], checkers: dict[str, Any] | None = None,
                  pilots: dict[str, str] | None = None) -> dict[str, Any]:
    """Report provisionability and scorability for one task, with the blockers named."""
    checkers = _CHECKERS if checkers is None else checkers
    pilots = PILOT_TASKS if pilots is None else pilots
    task_id, declared = str(task.get("id", "")), list(task.get("required_inputs") or [])
    oracle = dict(task.get("oracle") or {})
    checker_id = str(oracle.get("checker_id", ""))
    blockers: list[str] = []
    in_tree: list[str] = []
    typed: list[str] = []

    for reference in declared:
        state, detail = _input_state(Path(root).resolve(), reference)
        if state == "in_tree":
            in_tree.append(detail)
        elif state == "typed":
            typed.append(detail)
            if checker_id in checkers:
                # The manifest refuses this pairing and is right to. A scored task
                # is scored against a sealed workspace, so material the workspace
                # cannot hold would make the score unreadable.
                blockers.append(f"pilot_typed_input:{detail}")
        else:
            blockers.append(f"{state}:{reference}")

    provisionable = not any(row.startswith(_UNPROVISIONABLE) for row in blockers)
    if not oracle:
        blockers.append("no_oracle")
    elif checker_id not in checkers:
        blockers.append("checker_not_registered:" + (checker_id or "unset"))
    elif pilots.get(checker_id, task_id) != task_id:
        blockers.append(f"checker_bound_to_other_task:{pilots[checker_id]}")

    fixture = str(oracle.get("fixture", ""))
    if fixture and not (Path(root) / fixture).is_file():
        blockers.append(f"fixture_missing:{fixture}")

    scorable = checker_id in checkers and not any(row.startswith(_UNSCORABLE) for row in blockers)
    return {
        "task_id": task_id,
        "lane": str(task.get("lane", "")),
        "declared_inputs": len(declared),
        "provisioned_inputs": len(in_tree),
        "unprovisioned_inputs": typed,
        "checker_id": checker_id,
        "provisionable": provisionable,
        "scorable": scorable,
        "measured": provisionable and scorable,
        "blockers": sorted(set(blockers)),
    }


def evaluate_task_set(root: Path, task_set_path: Path) -> dict[str, Any]:
    """Read a task set and report both denominators with a verdict."""
    root = Path(root).resolve()
    body = json.loads(Path(task_set_path).read_bytes().decode("utf-8"))
    rows = [classify_task(root, task) for task in body.get("tasks", [])]
    counts = {
        "declared": len(rows),
        "provisionable": sum(1 for row in rows if row["provisionable"]),
        "scorable": sum(1 for row in rows if row["scorable"]),
        "measured": sum(1 for row in rows if row["measured"]),
    }
    if counts["declared"] and counts["measured"] == counts["declared"]:
        verdict = "TASK_SET_MEASURABLE"
    elif counts["provisionable"]:
        verdict = "TASK_SET_PARTIAL"
    else:
        verdict = "TASK_SET_BLOCKED"
    return {
        "schema": SCHEMA,
        "task_set_id": str(body.get("task_set_id", "")),
        "task_set_path": Path(task_set_path).as_posix(),
        "verdict": verdict,
        "counts": counts,
        "registered_checkers": sorted(_CHECKERS),
        "tasks": rows,
        "does_not_prove": [
            "A provisionable task is not a task a provider will answer well.",
            "A scorable task is not a scored task. The score comes from a run.",
            "An unprovisioned typed reference is declared, not delivered. The attempt "
            "launches without that material inside its sealed workspace.",
            "This reads the task set and the tree. It calls no provider and spends nothing.",
        ],
    }


def render_markdown(record: dict[str, Any]) -> str:
    """A table an operator can read without opening the JSON."""
    counts = record["counts"]
    declared = counts["declared"]
    lines = [
        "# Task set executability: " + record["task_set_id"], "",
        "Verdict: **" + record["verdict"] + "**", "",
        f"- provisionable: {counts['provisionable']} of {declared}",
        f"- scorable: {counts['scorable']} of {declared}",
        f"- measured (both): {counts['measured']} of {declared}", "",
        "| task | provisionable | scorable | inputs sealed | declared only | blockers |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in record["tasks"]:
        blockers = ", ".join(row["blockers"]) or "none"
        yes_no = ("yes" if row["provisionable"] else "no", "yes" if row["scorable"] else "no")
        lines.append(
            f"| {row['task_id']} | {yes_no[0]} | {yes_no[1]} "
            f"| {row['provisioned_inputs']}/{row['declared_inputs']} "
            f"| {len(row['unprovisioned_inputs'])} | {blockers} |")
    lines += ["", "## What this does not prove", ""]
    lines += ["- " + item for item in record["does_not_prove"]]
    return "\n".join(lines) + "\n"
