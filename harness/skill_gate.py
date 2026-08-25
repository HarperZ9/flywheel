"""skill_gate.py -- the skill-from-experience bridge.

A lesson says what the organization learned; a gate receipt proves the
procedure still passes its own checks today. Binding the two is what
turns an admitted lesson into a skill: build_skill_gate accepts only
an ADMITTED lesson (surfaced is not yet earned, retired is gone) whose
evidence is either a verified bench with every attempt passing or a
trace regression report with zero regressions over at least one task.
The binding stores digests, never payloads, and verify_skill_gate
re-derives the verdict from the binding's own recorded facts.
"""
from __future__ import annotations

import json
from pathlib import Path

from .evidence_json import canonical_sha256
from .lesson import MATCH, STATUS_ADMITTED, verify_lesson

SCHEMA = "flywheel.skill-gate/v1"
_REGISTRY_SCHEMA = "flywheel.skill-gate-registry/v1"
DRIFT = "DRIFT"


def _refuse(msg: str) -> None:
    raise ValueError(msg)


def _evidence_verdict(evidence: dict) -> tuple[str, int]:
    schema = evidence.get("schema")
    if schema == "flywheel.verified-bench/v1":
        attempts = evidence.get("attempts")
        denominator = evidence.get("denominator", {})
        if not isinstance(attempts, list) or not attempts:
            _refuse("bench evidence carries no attempts")
        if not all(a.get("gate_pass") is True for a in attempts):
            _refuse("the bench has failing attempts; skills bind on passes")
        return "verified_bench", len(attempts)
    if schema == "flywheel.trace-regression/v1":
        regressions = evidence.get("regressions")
        stable = evidence.get("stable", 0)
        improvements = evidence.get("improvements", [])
        new = evidence.get("new", [])
        covered = int(stable or 0) + len(improvements or []) + len(new or [])
        if regressions != []:
            _refuse("the regression report carries regressions")
        if covered < 1:
            _refuse("the regression report covers no tasks")
        return "trace_regression", covered
    _refuse(f"unsupported evidence schema: {schema!r}")


def build_skill_gate(*, lesson: dict, evidence: dict,
                     bound_at: str) -> dict:
    verdict = verify_lesson(lesson)
    if verdict["verdict"] != MATCH:
        _refuse("the lesson does not seal-verify")
    if lesson.get("status") != STATUS_ADMITTED:
        _refuse(f"only an admitted lesson becomes a skill "
                f"(this one is {lesson.get('status')!r})")
    kind, tasks = _evidence_verdict(evidence)
    body = {
        "schema": SCHEMA,
        "lesson_id": lesson["lesson_id"],
        "lesson_seal_hash": lesson["seal_hash"],
        "evidence_kind": kind,
        "evidence_sha256": canonical_sha256(evidence),
        "tasks_bound": tasks,
        "all_passed": True,
        "bound_at": bound_at,
        "does_not_prove": (
            "a bound gate says the procedure passed its checks when bound; "
            "it does not prove the claim holds beyond those tasks"),
    }
    body["gate_sha256"] = canonical_sha256(
        {k: v for k, v in body.items() if k != "gate_sha256"})
    return body


def verify_skill_gate(binding: dict) -> dict:
    """Recompute the verdict from the binding's own recorded facts."""
    required = ("lesson_id", "lesson_seal_hash", "evidence_kind",
                "evidence_sha256", "tasks_bound", "all_passed",
                "bound_at", "gate_sha256")
    missing = [f for f in required if f not in binding]
    if missing:
        return {"verdict": DRIFT, "reason": f"missing {sorted(missing)}"}
    expected = canonical_sha256(
        {k: v for k, v in binding.items() if k != "gate_sha256"})
    if expected != binding.get("gate_sha256"):
        return {"verdict": DRIFT, "reason": "gate seal does not reproduce"}
    if binding.get("all_passed") is not True or binding.get("tasks_bound", 0) < 1:
        return {"verdict": DRIFT,
                "reason": "a skill gate binds passing evidence only"}
    return {"verdict": MATCH, "reason": ""}


def save_skill_gates(rows: list[dict], *,
                     registry_path: Path) -> Path:
    for row in rows:
        if row.get("schema") != SCHEMA or verify_skill_gate(row)["verdict"] \
                != MATCH:
            _refuse("the registry holds only sealed skill gates")
    path = Path(registry_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r, sort_keys=True) for r in rows),
        encoding="utf-8")
    return path


def load_skill_gates(path: Path) -> list[dict]:
    p = Path(path)
    if not p.is_file():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("schema") != SCHEMA \
                or verify_skill_gate(row)["verdict"] != MATCH:
            _refuse("the registry holds an unsealed or tampered row")
        rows.append(row)
    return rows
