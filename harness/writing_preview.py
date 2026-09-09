"""Exact proposal previews for Writing Workspace approval."""
from __future__ import annotations

from typing import Callable

from .writing_artifacts import WritingArtifactStore
from .writing_reader_flow import scope_replacement_plan
from .writing_types import sha256_bytes


def build_proposal_preview(record: dict, *, artifacts: WritingArtifactStore,
                           owner_ref: str,
                           project_state: Callable[[str], dict]) -> dict:
    preview = {"schema": "flywheel.writing-proposal-preview/v1",
        "proposal_ref": record["proposal_ref"], "state": record["state"],
        "action": record["action"], "operation": record["operation"],
        "operation_sha256": record["grant_request"]["operation_sha256"],
        "request": record["request"]}
    command = record["request"].get("command", {})
    if command.get("type") != "record_writing_artifact":
        return preview
    artifact = artifacts.read_json(command["artifact_ref"], command["artifact_sha256"],
        expected_kind=command["kind"], expected_owner_ref=owner_ref)
    preview["writing_artifact"] = _artifact_summary(command, artifact)
    extra = _approval_preview(record, artifact, artifacts, owner_ref, project_state)
    if extra: preview["approval_preview"] = extra
    return preview


def _artifact_summary(command: dict, artifact: dict) -> dict:
    kind = command["kind"]
    return {"kind": kind, "artifact_ref": command["artifact_ref"],
        "artifact_sha256": command["artifact_sha256"],
        "artifact_id": artifact.get(f"{kind}_ref")}


def _approval_preview(record: dict, artifact: dict, artifacts: WritingArtifactStore,
                      owner_ref: str, project_state: Callable[[str], dict]) -> dict:
    kind = record["request"]["command"]["kind"]
    if kind == "revision":
        body = _read(artifacts, owner_ref, artifact)
        return {"kind": "revision", "section_ref": artifact["section_ref"],
            "base_revision_ref": artifact["base_revision_ref"],
            "body_sha256": artifact["body_sha256"], "word_count": artifact["word_count"],
            "text_admission": artifact["text_admission"], "body": body}
    if kind == "candidate":
        return _candidate_preview(record, artifact, artifacts, owner_ref, project_state)
    if kind == "decision":
        state = project_state(record["request"]["journey_ref"])
        candidate = state["candidates"].get(artifact.get("candidate_ref"), {})
        return {"kind": "decision", "decision": artifact["decision"],
            "section_ref": artifact["section_ref"], "reason": artifact["reason"],
            "from_revision_ref": artifact["from_revision_ref"],
            "to_revision_ref": artifact["to_revision_ref"],
            "scope_verdict": artifact["scope_verdict"],
            "candidate_scope_verdict": candidate.get("scope_receipt", {}).get("verdict")}
    if kind == "review":
        return {"kind": "review", "revision_refs": artifact["revision_refs"],
            "reader_flow_ref": artifact["reader_flow_ref"],
            "blocking_items": artifact["blocking_items"],
            "quality_measurement": artifact["quality_measurement"]}
    if kind == "export":
        return {"kind": "export", "included_sections": artifact["included_sections"],
            "decision_refs": artifact["decision_refs"], "review_ref": artifact["review_ref"],
            "source_packet_ref": artifact["source_packet_ref"],
            "manuscript_sha256": artifact["manuscript_sha256"]}
    return {}


def _candidate_preview(record: dict, candidate: dict, artifacts: WritingArtifactStore,
                       owner_ref: str, project_state: Callable[[str], dict]) -> dict:
    state = project_state(record["request"]["journey_ref"])
    card = state["cards"][candidate["card_ref"]]; target = card["target"]
    base = artifacts.read_text(state["revisions"][target["base_revision_ref"]]["body_ref"],
        target["base_body_sha256"], expected_owner_ref=owner_ref,
        expected_project_ref=candidate["project_ref"])
    body = _read(artifacts, owner_ref, candidate)
    scope = scope_replacement_plan(base, body, target)
    prefix, suffix = base[:target["start"]], base[target["end"]:]
    return {"kind": "candidate", "card_ref": candidate["card_ref"],
        "base_revision_ref": candidate["base_revision_ref"], "target": target,
        "candidate_body": body, "diff_summary": candidate["diff_summary"],
        "text_admission": candidate["text_admission"],
        "out_of_scope_changes": candidate["out_of_scope_changes"],
        "card_constraints": {"problem": card["problem"], "goal": card["goal"],
        "must_preserve": card["must_preserve"],
        "allowed_operations": card["allowed_operations"],
        "forbidden_operations": card["forbidden_operations"],
        "source_refs": card["source_refs"],
        "voice_constraints": card["voice_constraints"]},
        "scope_receipt": scope,
        "stored_scope_receipt_matches": scope == candidate["scope_receipt"],
        "preservation": {"prefix_sha256": sha256_bytes(prefix.encode()),
        "suffix_sha256": sha256_bytes(suffix.encode())}}


def _read(artifacts: WritingArtifactStore, owner_ref: str, artifact: dict) -> str:
    ref = artifact.get("body_ref") or artifact.get("candidate_body_ref")
    digest = artifact.get("body_sha256") or artifact.get("candidate_body_sha256")
    return artifacts.read_text(ref, digest, expected_owner_ref=owner_ref,
        expected_project_ref=artifact["project_ref"])
