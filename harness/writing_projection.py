"""Read-only Writing Workspace projection over Journey v2 events."""
from __future__ import annotations

from copy import deepcopy

from .journey_projection import reduce_events
from .writing_artifacts import WritingArtifactError, WritingArtifactStore
from .writing_state_rules import WritingStateError, validate_transition
from .writing_types import MAX_MANUSCRIPT_TEXT_BYTES, SCHEMAS

WRITING_PROJECTION_SCHEMA = "flywheel.writing-project-projection/v1"
_ARTIFACT_ID = {
    "section": "section_ref", "revision": "revision_ref",
    "diagnostic": "diagnostic_ref", "card": "card_ref",
    "candidate": "candidate_ref", "decision": "decision_ref",
    "review": "review_ref", "export": "export_ref",
}


class WritingProjectionError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def project_from_events(events: list[dict], artifacts: WritingArtifactStore) -> dict:
    """Replay committed Writing artifacts and reject semantic drift."""
    try:
        base = reduce_events(events)
        state, owner_ref = _initial_state(events[0], base)
        for event in events[1:]:
            for fact in event["payload"].get("facts", []):
                command = _command_from_fact(fact)
                if command is None:
                    continue
                artifact = _read_artifact(artifacts, command, owner_ref,
                                          state["project_ref"])
                validate_transition(state, command["kind"], artifact,
                                    artifacts, owner_ref)
                _apply_artifact(state, command, artifact, artifacts, owner_ref)
            state["event_head_sha256"] = event["event_sha256"]
        return state
    except WritingProjectionError:
        raise
    except WritingStateError as exc:
        raise WritingProjectionError(exc.code) from exc
    except WritingArtifactError as exc:
        raise WritingProjectionError(exc.code) from exc
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise WritingProjectionError("PROJECTION_INVALID") from exc


def validate_writing_append(journeys, artifacts: WritingArtifactStore,
                            request: dict, operation: str,
                            operation_body: dict) -> None:
    """Recompute the proposed Writing append before burning the grant."""
    try:
        command = _require_command(request.get("command"))
        if operation != "record_fact":
            raise WritingProjectionError("INVALID_TRANSITION")
        state = project_from_events(journeys._events(request["journey_ref"]),
                                    artifacts)
        if state["event_head_sha256"] != request["expected_event_head"]:
            from .evidence_public import TransportError
            raise TransportError("HEAD_CONFLICT", "Journey head changed", 409)
        artifact = _read_artifact(artifacts, command, journeys.owner_ref,
                                  state["project_ref"])
        validate_transition(state, command["kind"], artifact, artifacts,
                            journeys.owner_ref)
        from .writing_artifacts import record_fact_for_artifact
        expected = record_fact_for_artifact(
            artifacts, command, owner_ref=journeys.owner_ref,
            project_ref=state["project_ref"])
        if (type(operation_body) is not dict
                or set(operation_body) != {"occurred_at", "payload"}
                or type(operation_body.get("occurred_at")) is not str
                or operation_body.get("payload") != expected):
            raise WritingProjectionError("INVALID_TRANSITION")
    except WritingProjectionError:
        raise
    except WritingStateError as exc:
        raise WritingProjectionError(exc.code) from exc
    except WritingArtifactError as exc:
        raise WritingProjectionError(exc.code) from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise WritingProjectionError("INVALID_TRANSITION") from exc


def _initial_state(first_event: dict, base_projection: dict) -> tuple[dict, str | None]:
    payload = first_event["payload"]
    intake = deepcopy(payload.get("intake", {}))
    project_ref = intake.get("project_ref")
    owner_ref = _owner_from_intake(intake) if _is_writing_intake(intake) else None
    return ({
        "schema": WRITING_PROJECTION_SCHEMA,
        "journey_ref": first_event["journey_ref"],
        "event_head_sha256": first_event["event_sha256"],
        "project_ref": project_ref, "intake": intake,
        "journey_stage": base_projection.get("stage"),
        "section_order": [], "sections": {}, "revisions": {},
        "diagnostics": {}, "cards": {}, "candidates": {},
        "decisions": [], "reviews": [], "exports": [],
        "accepted_revision_refs_by_section": {},
    }, owner_ref)


def _is_writing_intake(intake: object) -> bool:
    return type(intake) is dict and intake.get("schema") == "flywheel.writing-intake/v1"


def _owner_from_intake(intake: dict) -> str:
    scopes = [_scope(ref) for ref in (
        intake.get("brief_ref"), intake.get("source_packet_ref"))]
    owners = {owner for owner, _project in scopes}
    projects = {project for _owner, project in scopes}
    if len(owners) != 1 or projects != {intake.get("project_ref")}:
        raise WritingProjectionError("PROJECT_MISMATCH")
    return next(iter(owners))


def _scope(artifact_ref: object) -> tuple[str, str]:
    if type(artifact_ref) is not str or "\\" in artifact_ref:
        raise WritingProjectionError("ARTIFACT_REF_INVALID")
    parts = artifact_ref.split("/")
    if (len(parts) < 8 or tuple(parts[:3]) != ("writing", "v1", "owners")
            or parts[4] != "projects"):
        raise WritingProjectionError("ARTIFACT_REF_INVALID")
    return parts[3], parts[5]


def _command_from_fact(fact: object) -> dict | None:
    if type(fact) is not dict:
        raise WritingProjectionError("INVALID_TRANSITION")
    fact_id = fact.get("fact_id")
    if type(fact_id) is not str or not fact_id.startswith("writing:"):
        return None
    parts = fact_id.split(":", 2)
    if len(parts) != 3 or parts[1] not in _ARTIFACT_ID:
        raise WritingProjectionError("INVALID_TRANSITION")
    refs = fact.get("receipt_refs")
    if (fact.get("receipt_state") != "MATCH" or type(refs) is not list
            or len(refs) != 1 or type(fact.get("artifact_sha256")) is not str):
        raise WritingProjectionError("INVALID_TRANSITION")
    return {"type": "record_writing_artifact", "kind": parts[1],
            "opaque_ref": parts[2], "artifact_ref": refs[0],
            "artifact_sha256": fact["artifact_sha256"]}


def _require_command(command: object) -> dict:
    if type(command) is not dict or set(command) != {
            "type", "kind", "artifact_ref", "artifact_sha256", "opaque_ref"}:
        raise WritingProjectionError("INVALID_TRANSITION")
    if command.get("type") != "record_writing_artifact" or command.get("kind") not in _ARTIFACT_ID:
        raise WritingProjectionError("INVALID_TRANSITION")
    return command


def _read_artifact(artifacts: WritingArtifactStore, command: dict,
                   owner_ref: str | None, project_ref: str) -> dict:
    artifact = artifacts.read_json(
        command["artifact_ref"], command["artifact_sha256"],
        expected_kind=command["kind"], expected_owner_ref=owner_ref,
        expected_project_ref=project_ref)
    if artifact.get(_ARTIFACT_ID[command["kind"]]) != command["opaque_ref"]:
        raise WritingProjectionError("ARTIFACT_REF_INVALID")
    return artifact


def _apply_artifact(state: dict, command: dict, artifact: dict,
                    artifacts: WritingArtifactStore, owner_ref: str | None) -> None:
    kind = command["kind"]
    stored = {**deepcopy(artifact), "artifact_ref": command["artifact_ref"],
              "artifact_sha256": command["artifact_sha256"]}
    if kind == "section":
        _apply_section(state, stored)
    elif kind == "revision":
        _apply_revision(state, stored, artifacts, owner_ref)
    elif kind == "diagnostic":
        state["diagnostics"][stored["diagnostic_ref"]] = stored
    elif kind == "card":
        state["cards"][stored["card_ref"]] = stored
    elif kind == "candidate":
        state["candidates"][stored["candidate_ref"]] = stored
    elif kind == "decision":
        _apply_decision(state, stored, artifacts, owner_ref)
    elif kind == "review":
        state["reviews"].append(stored)
    elif kind == "export":
        state["exports"].append(stored)


def _apply_section(state: dict, section: dict) -> None:
    prior = state["sections"].get(section["section_ref"], {})
    section.update({key: prior.get(key) for key in (
        "current_revision_ref", "current_body_ref", "current_body_sha256",
        "current_body")})
    state["sections"][section["section_ref"]] = section
    if section["section_ref"] not in state["section_order"]:
        state["section_order"].append(section["section_ref"])
    state["section_order"].sort(
        key=lambda ref: state["sections"][ref]["order_index"])
    state["accepted_revision_refs_by_section"].setdefault(
        section["section_ref"], [])


def _apply_revision(state: dict, revision: dict, artifacts: WritingArtifactStore,
                    owner_ref: str | None) -> None:
    state["revisions"][revision["revision_ref"]] = revision
    body = artifacts.read_text(
        revision["body_ref"], revision["body_sha256"],
        expected_owner_ref=owner_ref, expected_project_ref=state["project_ref"])
    _set_current_revision(state, revision, body)


def _apply_decision(state: dict, decision: dict, artifacts: WritingArtifactStore,
                    owner_ref: str | None) -> None:
    state["decisions"].append(decision)
    if decision["decision"] == "accept":
        _accept_candidate(state, state["candidates"][decision["candidate_ref"]],
                          artifacts, owner_ref)
    elif decision["decision"] == "rollback":
        revision = state["revisions"][decision["to_revision_ref"]]
        body = artifacts.read_text(
            revision["body_ref"], revision["body_sha256"],
            expected_owner_ref=owner_ref,
            expected_project_ref=state["project_ref"])
        _set_current_revision(state, revision, body)


def _accept_candidate(state: dict, candidate: dict,
                      artifacts: WritingArtifactStore,
                      owner_ref: str | None) -> None:
    card = state["cards"][candidate["card_ref"]]
    body = artifacts.read_text(
        candidate["candidate_body_ref"], candidate["candidate_body_sha256"],
        expected_owner_ref=owner_ref, expected_project_ref=state["project_ref"],
        max_bytes=MAX_MANUSCRIPT_TEXT_BYTES)
    revision = {"schema": SCHEMAS["revision"], "project_ref": state["project_ref"],
        "section_ref": card["target"]["section_ref"],
        "revision_ref": candidate["candidate_revision_ref"],
        "base_revision_ref": candidate["base_revision_ref"],
        "body_ref": candidate["candidate_body_ref"],
        "body_sha256": candidate["candidate_body_sha256"],
        "word_count": len(body.split()), "author_supplied": False,
        "scope_refs": [candidate["card_ref"]],
        "text_admission": candidate["text_admission"],
        "does_not_prove": candidate["does_not_prove"],
        "accepted_candidate_ref": candidate["candidate_ref"]}
    state["revisions"][revision["revision_ref"]] = revision
    _set_current_revision(state, revision, body)


def _set_current_revision(state: dict, revision: dict, body: str) -> None:
    section = state["sections"][revision["section_ref"]]
    section["current_revision_ref"] = revision["revision_ref"]
    section["current_body_ref"] = revision["body_ref"]
    section["current_body_sha256"] = revision["body_sha256"]
    section["current_body"] = body
    accepted = state["accepted_revision_refs_by_section"].setdefault(
        revision["section_ref"], [])
    if revision["revision_ref"] not in accepted:
        accepted.append(revision["revision_ref"])
