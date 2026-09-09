"""Project private Writing Workspace state from digest-bound Journey facts."""
from __future__ import annotations

from copy import deepcopy

from .evidence_public import TransportError
from .journey_store import JourneyStoreError, MutationCommand
from .writing_artifacts import WritingArtifactError, WritingArtifactStore
from .writing_state_rules import (
    WritingStateError, validate_decision, validate_transition,
)


class WritingProjectionError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


_ID_FIELDS = {
    "section": "section_ref", "revision": "revision_ref",
    "diagnostic": "diagnostic_ref", "card": "card_ref",
    "candidate": "candidate_ref", "decision": "decision_ref",
    "review": "review_ref", "export": "export_ref",
}


def project_from_events(events: list[dict], artifacts: WritingArtifactStore) -> dict:
    if not events:
        return {"projects": []}
    genesis = events[0]["payload"].get("intake", {})
    owner_ref = events[0].get("actor_id")
    state = {
        "project_ref": genesis.get("project_ref"),
        "journey_ref": events[0]["journey_ref"],
        "event_head_sha256": events[0]["event_sha256"],
        "intake": deepcopy(genesis),
        "sections": {}, "section_order": [], "revisions": {},
        "accepted_revision_refs_by_section": {},
        "diagnostics": {}, "cards": {}, "candidates": {},
        "decisions": [], "reviews": [], "exports": [],
    }
    for event in events[1:]:
        for fact in event["payload"].get("facts", []):
            _apply_fact(state, artifacts, fact, owner_ref)
        state["event_head_sha256"] = event["event_sha256"]
    _attach_current_bodies(state, artifacts, owner_ref)
    return state


def validate_writing_append(service, artifacts: WritingArtifactStore, req: dict,
                            operation: str, body: dict) -> None:
    if operation != "record_fact" or _is_exact_replay(service, req, operation, body):
        return
    facts = body.get("payload", {}).get("facts") if type(body) is dict else None
    writing_facts = [fact for fact in facts or [] if _fact_kind(fact)]
    if not writing_facts:
        return
    events = service._events(req["journey_ref"])
    if not events or events[-1]["event_sha256"] != req["expected_event_head"]:
        raise TransportError("HEAD_CONFLICT", "writing state head changed", 409)
    project_ref = events[0]["payload"].get("intake", {}).get("project_ref")
    if events[0]["payload"].get("intake", {}).get("schema") != "flywheel.writing-intake/v1":
        raise TransportError("INVALID_TRANSITION", "writing journey is unavailable", 422)
    try:
        state = project_from_events(events, artifacts)
    except (WritingArtifactError, WritingProjectionError, WritingStateError) as exc:
        _fail(getattr(exc, "code", "INVALID_TRANSITION"), True, exc)
    for fact in writing_facts:
        kind, artifact = _artifact_for_fact(
            fact, artifacts, service.owner_ref, project_ref, as_transport=True)
        try:
            validate_transition(state, kind, artifact, artifacts, service.owner_ref)
            _apply_artifact(state, kind, artifact, artifacts, service.owner_ref)
        except (WritingArtifactError, WritingProjectionError, WritingStateError) as exc:
            _fail(getattr(exc, "code", "INVALID_TRANSITION"), True, exc)


def _is_exact_replay(service, req: dict, operation: str, body: dict) -> bool:
    command = MutationCommand(
        owner_ref=service.owner_ref, journey_ref=req["journey_ref"],
        expected_event_head=req["expected_event_head"],
        client_request_id=req["client_request_id"],
        operation=operation, body=body)
    try:
        return service.store.lookup_replay(command) is not None
    except JourneyStoreError:
        raise


def _apply_fact(state: dict, artifacts: WritingArtifactStore, fact: dict,
                owner_ref: str | None) -> None:
    kind, artifact = _artifact_for_fact(
        fact, artifacts, owner_ref, state["project_ref"], as_transport=False)
    if kind is None:
        return
    try:
        validate_transition(state, kind, artifact, artifacts, owner_ref)
        _apply_artifact(state, kind, artifact, artifacts, owner_ref)
    except WritingStateError as exc:
        raise WritingProjectionError(exc.code) from exc


def _apply_artifact(state: dict, kind: str, artifact: dict,
                    artifacts: WritingArtifactStore | None = None,
                    owner_ref: str | None = None) -> None:
    if kind == "section":
        section = deepcopy(artifact); ref = section["section_ref"]
        previous = state["sections"].get(ref, {})
        state["sections"][ref] = {
            **section,
            "current_revision_ref": previous.get("current_revision_ref"),
            "current_body_ref": previous.get("current_body_ref"),
            "current_body_sha256": previous.get("current_body_sha256"),
        }
        state["accepted_revision_refs_by_section"].setdefault(ref, [])
        state["section_order"] = sorted(
            state["sections"],
            key=lambda name: (state["sections"][name]["order_index"], name),
        )
    elif kind == "revision":
        _record_revision(state, artifact, accepted=True)
    elif kind in {"diagnostic", "card", "candidate"}:
        state[f"{kind}s"][artifact[f"{kind}_ref"]] = deepcopy(artifact)
    elif kind == "decision":
        state["decisions"].append(deepcopy(artifact))
        _apply_decision(state, artifact, artifacts, owner_ref)
    elif kind == "review":
        state["reviews"].append(deepcopy(artifact))
    elif kind == "export":
        state["exports"].append(deepcopy(artifact))


def _artifact_for_fact(fact: dict, artifacts: WritingArtifactStore,
                       owner_ref: str | None, project_ref: str | None,
                       *, as_transport: bool) -> tuple[str | None, dict | None]:
    kind = _fact_kind(fact)
    if kind is None:
        return None, None
    refs, digest = fact.get("receipt_refs"), fact.get("artifact_sha256")
    if type(refs) is not list or len(refs) != 1 or type(digest) is not str:
        _fail("ARTIFACT_RECEIPT_INVALID", as_transport)
    try:
        artifact = artifacts.read_json(
            refs[0], digest, expected_kind=kind,
            expected_owner_ref=owner_ref, expected_project_ref=project_ref)
    except WritingArtifactError as exc:
        _fail(exc.code, as_transport, exc)
    artifact["artifact_ref"] = refs[0]
    artifact["artifact_sha256"] = digest
    if _identity(kind, artifact) != fact["fact_id"].rsplit(":", 1)[1]:
        _fail("ARTIFACT_IDENTITY_MISMATCH", as_transport)
    return kind, artifact


def _fact_kind(fact: object) -> str | None:
    fact_id = fact.get("fact_id") if type(fact) is dict else None
    if type(fact_id) is not str or not fact_id.startswith("writing:"):
        return None
    parts = fact_id.split(":", 2)
    return parts[1] if len(parts) == 3 and parts[1] in _ID_FIELDS else None


def _identity(kind: str, artifact: dict) -> str:
    value = artifact.get(_ID_FIELDS[kind])
    if type(value) is not str:
        raise WritingProjectionError("ARTIFACT_IDENTITY_MISMATCH")
    return value


def _record_revision(state: dict, revision: dict, *, accepted: bool) -> None:
    ref, section_ref = revision["revision_ref"], revision["section_ref"]
    state["revisions"][ref] = deepcopy(revision)
    section = state["sections"].setdefault(section_ref, {
        "section_ref": section_ref, "order_index": 10_000, "heading": section_ref,
        "purpose": "implicit section from revision", "reader_entry_state": "unknown",
        "promises": [], "current_revision_ref": None, "current_body_ref": None,
        "current_body_sha256": None,
    })
    if accepted:
        accepted_refs = state["accepted_revision_refs_by_section"].setdefault(
            section_ref, [])
        if ref not in accepted_refs:
            accepted_refs.append(ref)
    _set_current(section, revision)
    if section_ref not in state["section_order"]:
        state["section_order"].append(section_ref)


def _apply_decision(state: dict, decision: dict,
                    artifacts: WritingArtifactStore | None,
                    owner_ref: str | None) -> None:
    validate_decision(state, decision)
    section = state["sections"][decision["section_ref"]]
    if decision["decision"] in {"reject", "supersede"}:
        return
    if decision["decision"] == "rollback":
        _set_current(section, state["revisions"][decision["to_revision_ref"]])
        return
    candidate = state["candidates"][decision["candidate_ref"]]
    revision = {
        "schema": "flywheel.writing-revision/v1",
        "project_ref": decision["project_ref"],
        "section_ref": decision["section_ref"],
        "revision_ref": candidate["candidate_revision_ref"],
        "base_revision_ref": decision["from_revision_ref"],
        "body_ref": candidate["candidate_body_ref"],
        "body_sha256": candidate["candidate_body_sha256"],
        "word_count": len(_read_candidate_body(state, candidate, artifacts, owner_ref).split()),
        "author_supplied": False, "scope_refs": [candidate["card_ref"]],
        "does_not_prove": candidate["does_not_prove"],
        "artifact_ref": candidate["artifact_ref"],
        "artifact_sha256": candidate["artifact_sha256"],
        "accepted_candidate_ref": candidate["candidate_ref"],
    }
    _record_revision(state, revision, accepted=True)


def _read_candidate_body(state: dict, candidate: dict,
                         artifacts: WritingArtifactStore | None,
                         owner_ref: str | None) -> str:
    if artifacts is None:
        return ""
    return artifacts.read_text(candidate["candidate_body_ref"],
        candidate["candidate_body_sha256"], expected_owner_ref=owner_ref,
        expected_project_ref=state["project_ref"])

def _set_current(section: dict, revision: dict) -> None:
    section["current_revision_ref"] = revision["revision_ref"]
    section["current_body_ref"] = revision["body_ref"]
    section["current_body_sha256"] = revision["body_sha256"]


def _attach_current_bodies(state: dict, artifacts: WritingArtifactStore,
                           owner_ref: str | None) -> None:
    for section in state["sections"].values():
        ref = section.get("current_body_ref")
        digest = section.get("current_body_sha256")
        section["current_body"] = artifacts.read_text(
            ref, digest, expected_owner_ref=owner_ref,
            expected_project_ref=state["project_ref"]) if ref and digest else None


def _fail(code: str, as_transport: bool, exc: Exception | None = None):
    if as_transport:
        raise TransportError(code, "writing append is unavailable", 403) from exc
    raise WritingProjectionError(code) from exc
