"""The extension routes: absent, unknown, stale, or execution-locked
capabilities deny before any dispatch; an accepted capability serves its
typed projection. No provider, model, or network call exists here."""
import pytest

from harness.evidence_extension_contracts import capability_document
from harness.evidence_extension_route import (
    handle_capabilities,
    handle_domain_pack_project,
    handle_frontier_axis,
    handle_frontier_project,
    handle_incident_propose,
)
from harness.frontier_claim import new_frontier_claim
from harness.incident_case import new_incident_case

JOURNEY = {"schema": "flywheel.evidence-journey-projection/v2",
           "event_head_sha256": "a" * 64}
RECEIPT = {"accepted": True, "receipt_sha256": "b" * 64}
INCIDENT = {
    "schema": "flywheel.incident-case/v1",
    "operations": ["incident.propose"],
    "limits": {"max_source_refs": 32},
    "acceptance_receipt": RECEIPT,
    "data_only": True,
}
FRONTIER = {
    "schema": "flywheel.frontier-claim/v1",
    "operations": ["frontier.project", "frontier.axis.append"],
    "limits": {"max_axes": 4},
    "acceptance_receipt": RECEIPT,
    "data_only": True,
}


def _sheet(containment=None):
    return capability_document(
        journey=JOURNEY, incident_contract=INCIDENT,
        frontier_contract=FRONTIER, pack_contracts=[],
        containment=containment or {"process": True})


def _case():
    return new_incident_case(
        case_id="case_" + "a" * 8, journey_ref="jrn_" + "a" * 32,
        event_head_sha256="a" * 64,
        source_refs=[{"fact_id": "fact_" + "a" * 8,
                      "statement": "the gate refused"}],
        failure={"summary": "check failed on the submitted object"},
        created_at="2026-08-22T12:00:00Z")


def _claim():
    return new_frontier_claim(
        claim_id="clm_" + "a" * 8, journey_ref="jrn_" + "a" * 32,
        source={"title": "t"}, proposition={"statement": "s"},
        created_at="2026-08-22T12:00:00Z",
        novelty_state="NOT_FOUND_IN_CORPUS")


def _incident_body(contract=None):
    from harness.evidence_json import canonical_sha256
    return {"capability_sha256": canonical_sha256(contract or INCIDENT),
            "case": _case(),
            "projection": {"journey_ref": "jrn_" + "a" * 32,
                           "event_head_sha256": "a" * 64,
                           "facts": [{"fact_id": "fact_" + "a" * 8,
                                      "statement": "the gate refused"}]}}


def _frontier_body():
    from harness.evidence_json import canonical_sha256
    return {"capability_sha256": canonical_sha256(FRONTIER),
            "journey_ref": "jrn_" + "a" * 32,
            "event_head_sha256": "a" * 64,
            "claim": _claim()}


def test_capabilities_route_serves_the_sheet():
    body, code = handle_capabilities(_sheet())
    assert code == 200
    assert body["schema"] == "flywheel.evidence-capabilities/v1"


def test_absent_capability_denies_before_dispatch():
    _, code = handle_incident_propose(_incident_body(), capability_document(
        journey=JOURNEY, incident_contract=None, frontier_contract=None,
        pack_contracts=[], containment={"process": True}))
    assert code == 403


def test_stale_contract_hash_denies():
    _, code = handle_incident_propose(_incident_body(contract={
        **INCIDENT, "limits": {"max_source_refs": 999}}),
        _sheet())
    assert code == 403


def test_execution_locked_denies():
    _, code = handle_incident_propose(_incident_body(),
                                      _sheet(containment={"process": False}))
    assert code == 403


def test_accepted_capability_compiles_the_proposal():
    body, code = handle_incident_propose(_incident_body(), _sheet())
    assert code == 200
    assert body["state"] == "proposed"


def test_frontier_project_preserves_raw_nulls():
    body, code = handle_frontier_project(_frontier_body(), _sheet())
    assert code == 200
    value = next(a for a in body["axes"] if a["axis"] == "value")
    assert value["fields"]["novelty_state"] == "NOT_FOUND_IN_CORPUS"


def test_frontier_axis_requires_a_valid_binding():
    body = {**_frontier_body(), "axis": "value",
            "patch": {"novelty_state": "known"},
            "expected_event_head": "a" * 64,
            "client_request_id": "req-1", "grant_ref": "gnt_" + "a" * 32,
            "claim_id": "clm_" + "a" * 8, "owner_ref": "owner_" + "a" * 32}
    body["capability_sha256"] = body.get("capability_sha256")
    event, code = handle_frontier_axis(body, _sheet(), lambda: "now")
    assert code == 200
    assert event["admitted_at"] == "now"

    cross = {**body, "axis": "identification",
             "patch": {"novelty_state": "novel"}}
    _, denied = handle_frontier_axis(cross, _sheet(), lambda: "now")
    assert denied == 403


def test_domain_pack_denies_an_unregistered_pack():
    body = {"capability_sha256": "d" * 64, "fixtures_root": "tests/fixtures",
            "manifest": {"schema": "flywheel.domain-pack/v1"},
            "fixtures": []}
    _, code = handle_domain_pack_project(body, _sheet())
    assert code == 403
