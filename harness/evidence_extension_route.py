"""evidence_extension_route.py -- capability-gated contextual routes.

GET  /api/journeys/capabilities        the fail-closed capability sheet
POST /api/journeys/incident-propose    deterministic incident proposal
POST /api/journeys/frontier-project    the four independent axes
POST /api/journeys/frontier-axis       one typed CAS axis event (grant)
POST /api/journeys/domain-pack-project pack manifest + QA projection

The gateway derives the capability sheet from its server-side registry
of accepted contracts; until contracts are accepted the sheet has zero
rows and every extension denies. Every handler re-checks the sheet
server-side: absent, unknown, stale, or execution-locked capabilities
deny before any dispatch. No provider, model, or network call exists
in this module.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from .evidence_extension_contracts import (
    authorize_capability,
    capability_document,
)
from .evidence_public import TransportError, error_response
from .frontier_claim_projection import append_frontier_axis_event
from .incident_proposal import compile_incident_proposal

_PACKET_SCHEMA = "flywheel.evidence-packet/v1"


def _deny(message: str) -> tuple[dict, int]:
    return error_response(
        TransportError("PERMISSION_DENIED", message, 403))


def _invalid(message: str) -> tuple[dict, int]:
    return error_response(TransportError("INVALID_REQUEST", message, 422))


def capabilities_for(journey_ref: str, event_head_sha256: str,
                     *, incident_contract=None, frontier_contract=None,
                     pack_contracts=None, containment=None) -> dict:
    """The sheet the gateway serves: empty until contracts are accepted."""
    return capability_document(
        journey={"schema": "flywheel.evidence-journey-projection/v2",
                 "event_head_sha256": event_head_sha256},
        incident_contract=incident_contract,
        frontier_contract=frontier_contract,
        pack_contracts=pack_contracts or [],
        containment=containment or {"process": False},
    )


def handle_capabilities(capabilities: dict) -> tuple[dict, int]:
    if capabilities.get("schema") != "flywheel.evidence-capabilities/v1":
        return _invalid("the capability sheet is malformed")
    return capabilities, 200


def _authorized(capabilities: dict, capability_id: str, operation: str,
                contract_sha256: str) -> tuple[dict, int] | None:
    if capabilities.get("schema") != "flywheel.evidence-capabilities/v1":
        return _invalid("the capability sheet is malformed")
    if not authorize_capability(
            capabilities, capability_id=capability_id, operation=operation,
            journey_schema=capabilities.get("journey_schema", ""),
            packet_schema=_PACKET_SCHEMA,
            contract_sha256=contract_sha256):
        return _deny("the capability is absent, unknown, or "
                     "execution-locked")
    return None


def handle_incident_propose(body: dict, capabilities: dict) -> tuple[dict, int]:
    try:
        contract_sha = body["capability_sha256"]
        case = body["case"]
        projection = body["projection"]
    except (KeyError, TypeError):
        return _invalid("the proposal request is incomplete")
    denied = _authorized(capabilities, "incident-compiler",
                         "incident.propose", contract_sha)
    if denied:
        return denied
    try:
        proposal = compile_incident_proposal(
            case=case, projection=projection,
            capability_sha256=contract_sha)
    except ValueError as exc:
        return _invalid(str(exc))
    return proposal, 200


def handle_frontier_project(body: dict, capabilities: dict) -> tuple[dict, int]:
    try:
        claim = body["claim"]
        journey_ref = body["journey_ref"]
        head = body["event_head_sha256"]
    except (KeyError, TypeError):
        return _invalid("the projection request is incomplete")
    contract_sha = body.get("capability_sha256", "")
    denied = _authorized(capabilities, "frontier-claims",
                         "frontier.project", contract_sha)
    if denied:
        return denied
    from .frontier_claim_projection import project_frontier_axes
    try:
        axes = project_frontier_axes(claim=claim, journey_ref=journey_ref,
                                     event_head_sha256=head)
    except ValueError as exc:
        return _invalid(str(exc))
    axes["capability_sha256"] = contract_sha
    return axes, 200


def handle_frontier_axis(body: dict, capabilities: dict,
                         clock: Callable[[], str]) -> tuple[dict, int]:
    required = ("journey_ref", "expected_event_head", "client_request_id",
                "grant_ref", "claim_id", "axis", "patch")
    if any(not body.get(field) for field in required):
        return _invalid("the axis event is incomplete")
    denied = _authorized(capabilities, "frontier-claims",
                         "frontier.axis.append",
                         body.get("capability_sha256", ""))
    if denied:
        return denied
    try:
        event = append_frontier_axis_event(
            owner_ref=body.get("owner_ref", ""),
            journey_ref=body["journey_ref"],
            expected_event_head=body["expected_event_head"],
            client_request_id=body["client_request_id"],
            grant_ref=body["grant_ref"],
            claim_id=body["claim_id"],
            axis=body["axis"],
            patch=body["patch"],
        )
    except ValueError as exc:
        return _deny(str(exc))
    event["admitted_at"] = clock()
    return event, 200


def handle_domain_pack_project(body: dict, capabilities: dict) -> tuple[dict, int]:
    manifest = body.get("manifest")
    fixtures = body.get("fixtures", [])
    if not isinstance(manifest, dict):
        return _invalid("the pack request is incomplete")
    contract_sha = body.get("capability_sha256", "")
    denied = _authorized(capabilities, manifest.get("pack_id", "unknown"),
                         "pack.project", contract_sha)
    if denied:
        return denied
    from .domain_pack import run_pack_qa, verify_pack_manifest
    try:
        admitted = verify_pack_manifest(
            manifest,
            fixtures_root=Path(body.get("fixtures_root", ".")))
    except ValueError as exc:
        return _invalid(str(exc))
    qa = run_pack_qa(admitted, fixtures)
    return {"schema": "flywheel.domain-pack-projection/v1",
            "pack": admitted, "qa": qa}, 200
