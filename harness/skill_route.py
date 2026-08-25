"""skill_route.py -- skill-gate routes.

GET  /api/skills       list bound skill gates
POST /api/skills/bind  bind an admitted lesson to passing gate evidence

The registry persists at <run_root>/skills/gates.jsonl and holds only
sealed rows; a tampered row refuses to load rather than degrading.
"""
from __future__ import annotations

from pathlib import Path

from .evidence_public import TransportError, error_response
from .skill_gate import (
    build_skill_gate,
    load_skill_gates,
    save_skill_gates,
)


def _invalid(message: str) -> tuple[dict, int]:
    return error_response(TransportError("INVALID_REQUEST", message, 422))


def _registry_path(run_root: Path) -> Path:
    return Path(run_root) / "skills" / "gates.jsonl"


def handle_skills_get(path: str, *, run_root) -> tuple[dict, int]:
    if path == "/api/skills":
        rows = load_skill_gates(_registry_path(Path(run_root)))
        return {"schema": "flywheel.skill-list/v1",
                "skills": rows, "count": len(rows)}, 200
    return error_response(TransportError("NOT_FOUND",
                                         "unknown skill route", 404))


def handle_skills_post(path: str, body: dict, *, run_root,
                       clock=None) -> tuple[dict, int]:
    action = path.rsplit("/", 1)[-1]
    if action != "bind":
        return error_response(TransportError("NOT_FOUND",
                                             "unknown skill route", 404))
    if not isinstance(body, dict):
        return _invalid("the bind request is a JSON object")
    lesson = body.get("lesson")
    evidence = body.get("evidence")
    if not isinstance(lesson, dict) or not isinstance(evidence, dict):
        return _invalid("bind carries a lesson and gate evidence")
    try:
        binding = build_skill_gate(
            lesson=lesson, evidence=evidence,
            bound_at=str(body.get("bound_at") or (clock() if clock else "")))
    except ValueError as exc:
        return _invalid(str(exc))
    path_reg = _registry_path(Path(run_root))
    rows = [r for r in load_skill_gates(path_reg)
            if r["lesson_id"] != binding["lesson_id"]
            or r["gate_sha256"] != binding["gate_sha256"]]
    rows.append(binding)
    save_skill_gates(rows, registry_path=path_reg)
    return {"schema": "flywheel.skill-bind-ack/v1",
            "skill_gate": binding}, 200
