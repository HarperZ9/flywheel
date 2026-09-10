"""Bind an admitted lesson to consistent, self-reported benchmark evidence.

MATCH checks integrity and recorded task coverage, not evaluator identity,
procedure execution, or semantic truth. Old sealed v1 rows remain readable
as UNVERIFIED; loading never silently upgrades or rewrites their payloads.
"""
from __future__ import annotations

import json
from pathlib import Path

from .evidence_json import canonical_sha256
from .lesson import MATCH, STATUS_ADMITTED, verify_lesson
from .skill_evidence import (
    digest, require, summarize_evidence, summary_source_digest, validate_summary,
)

SCHEMA = "flywheel.skill-gate/v2"
LEGACY_SCHEMA = "flywheel.skill-gate/v1"
_REGISTRY_SCHEMA = "flywheel.skill-gate-registry/v1"
DRIFT = "DRIFT"
UNVERIFIED = "UNVERIFIED"
LIMIT = ("Self-reported evidence consistency only. Hashes do not authenticate "
         "the evaluator, show that this lesson's procedure was used, or prove "
         "semantic correctness, safety, or performance beyond the recorded tasks.")


def _refuse(msg: str) -> None:
    raise ValueError(msg)


def build_skill_gate(*, lesson: dict, evidence: dict,
                     bound_at: str, prior_bench=None, current_bench=None) -> dict:
    require(isinstance(lesson, dict) and isinstance(bound_at, str),
            "lesson must be an object and bound_at a string")
    verdict = verify_lesson(lesson)
    if verdict["verdict"] != MATCH:
        _refuse("the lesson does not seal-verify")
    if lesson.get("status") != STATUS_ADMITTED:
        _refuse(f"only an admitted lesson becomes a skill "
                f"(this one is {lesson.get('status')!r})")
    summary = summarize_evidence(evidence, prior_bench=prior_bench,
                                 current_bench=current_bench)
    body = {
        "schema": SCHEMA,
        "lesson_id": lesson["lesson_id"],
        "lesson_seal_hash": lesson["seal_hash"],
        "evidence_kind": summary["kind"],
        "evidence_sha256": canonical_sha256(evidence),
        "evidence_summary": summary,
        "tasks_bound": len(summary["current"]["tasks"]),
        "attempts_bound": len(summary["current"]["attempts"]),
        "all_passed": True,
        "evidence_origin": "self_reported",
        "independent_evaluation": UNVERIFIED,
        "procedure_application": "UNKNOWN",
        "bound_at": bound_at,
        "does_not_prove": LIMIT,
    }
    body["gate_sha256"] = canonical_sha256(
        {k: v for k, v in body.items() if k != "gate_sha256"})
    return body


def verify_skill_gate(binding: dict, *, evidence=None,
                      prior_bench=None, current_bench=None) -> dict:
    """Check the projection; optionally rebind the exact original sources."""
    result = {"verdict": DRIFT, "reason": "", "integrity": DRIFT,
              "source_binding": "NOT_RECHECKED", "evidence_origin": "self_reported",
              "independent_evaluation": UNVERIFIED,
              "procedure_application": "UNKNOWN", "does_not_prove": LIMIT}
    try:
        require(isinstance(binding, dict), "binding must be an object")
        schema = binding.get("schema")
        require(schema in (SCHEMA, LEGACY_SCHEMA), "unknown skill binding schema")
        for field in ("lesson_id", "lesson_seal_hash", "evidence_sha256", "gate_sha256"):
            require(digest(binding.get(field)), f"invalid {field}")
        require(binding["lesson_id"] == binding["lesson_seal_hash"],
                "lesson identity disagrees with its seal")
        require(binding["gate_sha256"] == canonical_sha256(
            {k: v for k, v in binding.items() if k != "gate_sha256"}),
            "gate seal does not reproduce")
        require(binding.get("all_passed") is True
                and type(binding.get("tasks_bound")) is int and binding["tasks_bound"] > 0,
                "binding has no reported passing coverage")
        require(binding.get("evidence_kind") in ("verified_bench", "trace_regression")
                and isinstance(binding.get("bound_at"), str), "invalid binding metadata")
        if schema == LEGACY_SCHEMA:
            return dict(result, verdict=UNVERIFIED, integrity=MATCH,
                        source_binding="LEGACY_NOT_VALIDATED",
                        reason="legacy seal matches; source/task coverage was not validated")
        require(binding.get("evidence_origin") == "self_reported"
                and binding.get("independent_evaluation") == UNVERIFIED
                and binding.get("procedure_application") == "UNKNOWN"
                and binding.get("does_not_prove") == LIMIT,
                "binding overstates its assurance")
        summary = binding.get("evidence_summary")
        validate_summary(summary)
        require(summary["kind"] == binding["evidence_kind"]
                and binding["tasks_bound"] == len(summary["current"]["tasks"])
                and type(binding.get("attempts_bound")) is int
                and binding["attempts_bound"] == len(summary["current"]["attempts"]),
                "binding counts/kind disagree with its evidence projection")
        require(binding["evidence_sha256"] == summary_source_digest(summary),
                "evidence source digest disagrees with projection")
        if evidence is not None:
            actual = summarize_evidence(evidence, prior_bench=prior_bench,
                                        current_bench=current_bench)
            require(canonical_sha256(evidence) == binding["evidence_sha256"]
                    and canonical_sha256(actual) == canonical_sha256(summary),
                    "supplied sources do not match this binding")
            result["source_binding"] = MATCH
        else:
            require(prior_bench is None and current_bench is None,
                    "source benches require the bound evidence document")
        return dict(result, verdict=MATCH, integrity=MATCH)
    except (ValueError, TypeError, KeyError) as exc:
        return dict(result, reason=str(exc))


def save_skill_gates(rows: list[dict], *,
                     registry_path: Path) -> Path:
    for row in rows:
        if verify_skill_gate(row)["verdict"] not in (MATCH, UNVERIFIED):
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
        if verify_skill_gate(row)["verdict"] not in (MATCH, UNVERIFIED):
            _refuse("the registry holds an unsealed or tampered row")
        rows.append(row)
    return rows
