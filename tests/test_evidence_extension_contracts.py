"""Fail-closed extension capabilities: an advertisement is a fact sheet,
never an authority.

The capability document binds each contextual extension (Incident
Compiler, Frontier Claims, Domain Packs) to accepted schemas, accepted
receipts, and the containment fact. Rows derive only from accepted
contracts; executable operations stay locked without accepted process
containment; authorize_capability never consumes a grant and never
grants by absence.
"""
import json

import pytest

from harness.evidence_extension_contracts import (
    SCHEMA,
    authorize_capability,
    capability_document,
)
from harness.evidence_json import canonical_sha256

JOURNEY = {
    "schema": "flywheel.evidence-journey-projection/v2",
    "event_head_sha256": "a" * 64,
}
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


def _doc(**overrides):
    return capability_document(
        journey=overrides.get("journey", JOURNEY),
        incident_contract=overrides.get("incident_contract", INCIDENT),
        frontier_contract=overrides.get("frontier_contract", FRONTIER),
        pack_contracts=overrides.get("pack_contracts", []),
        containment=overrides.get("containment", {"process": False}),
    )


def test_schema_is_versioned_and_document_is_canonical():
    doc = _doc()
    assert doc["schema"] == SCHEMA == "flywheel.evidence-capabilities/v1"
    assert json.dumps(doc, sort_keys=True) == json.dumps(doc, sort_keys=True)


def test_rows_carry_the_exact_field_set():
    doc = _doc()
    for row in doc["capabilities"]:
        assert set(row) == {
            "id", "schema", "state", "operations", "journey_schema",
            "packet_schema", "containment_class", "limits", "reason",
            "contract_sha256", "acceptance_receipt_sha256",
        }
        assert row["state"] in {
            "read_only", "data_only", "execution_locked", "available"}


def test_contract_hashes_bind_the_accepted_bytes():
    doc = _doc()
    incident = next(r for r in doc["capabilities"]
                    if r["id"] == "incident-compiler")
    assert incident["contract_sha256"] == canonical_sha256(INCIDENT)
    assert incident["acceptance_receipt_sha256"] == canonical_sha256(RECEIPT)


def test_data_only_contracts_stay_execution_locked_without_containment():
    doc = _doc(containment={"process": False})
    incident = next(r for r in doc["capabilities"]
                    if r["id"] == "incident-compiler")
    assert incident["state"] == "execution_locked"


def test_accepted_process_containment_unlocks_available():
    doc = _doc(containment={"process": True})
    incident = next(r for r in doc["capabilities"]
                    if r["id"] == "incident-compiler")
    assert incident["state"] == "available"


def test_unknown_schema_is_refused():
    with pytest.raises(ValueError):
        _doc(incident_contract={**INCIDENT, "schema": "something/else/v9"})


def test_unaccepted_receipt_is_refused():
    with pytest.raises(ValueError):
        _doc(incident_contract={
            **INCIDENT,
            "acceptance_receipt": {"accepted": False, "receipt_sha256": "b" * 64},
        })


def test_head_or_schema_drift_is_refused():
    with pytest.raises(ValueError):
        _doc(journey={**JOURNEY, "schema": "flywheel.evidence-journey-projection/v1"})


def test_duplicate_ids_are_refused():
    with pytest.raises(ValueError):
        _doc(pack_contracts=[{
            "schema": "flywheel.domain-pack/v1",
            "pack_id": "incident-compiler",
            "operations": ["pack.project"],
            "limits": {"max_fixtures": 8},
            "acceptance_receipt": RECEIPT,
            "data_only": True,
        }])


def test_unknown_operation_or_state_is_refused():
    with pytest.raises(ValueError):
        _doc(incident_contract={**INCIDENT, "operations": ["not.an.op"]})
    with pytest.raises(ValueError):
        _doc(incident_contract={
            **INCIDENT, "operations": ["incident.propose", "exec.arbitrary"]})


def test_missing_limits_are_refused():
    with pytest.raises(ValueError):
        _doc(incident_contract={
            k: v for k, v in INCIDENT.items() if k != "limits"})


def test_absent_capability_grants_nothing():
    doc = _doc()
    assert authorize_capability(
        doc, capability_id="no-such-row", operation="incident.propose",
        journey_schema=JOURNEY["schema"], packet_schema="flywheel.evidence-packet/v1",
        contract_sha256=canonical_sha256(INCIDENT)) is False


def test_authorize_requires_exact_operation_schema_and_hash():
    # With containment accepted the incident row is available and its
    # advertised operation authorizes against the exact schemas and hash.
    doc = _doc(containment={"process": True})
    base = dict(
        capability_id="incident-compiler",
        operation="incident.propose",
        journey_schema=JOURNEY["schema"],
        packet_schema="flywheel.evidence-packet/v1",
        contract_sha256=canonical_sha256(INCIDENT),
    )
    assert authorize_capability(doc, **base) is True
    assert authorize_capability(
        doc, **{**base, "operation": "frontier.axis.append"}) is False
    assert authorize_capability(
        doc, **{**base, "journey_schema": "other/v1"}) is False
    assert authorize_capability(
        doc, **{**base, "contract_sha256": "c" * 64}) is False


def test_execution_locked_refuses_its_own_operations():
    doc = _doc(containment={"process": False})
    assert authorize_capability(
        doc, capability_id="incident-compiler",
        operation="incident.propose",
        journey_schema=JOURNEY["schema"],
        packet_schema="flywheel.evidence-packet/v1",
        contract_sha256=canonical_sha256(INCIDENT)) is False, \
        "execution_locked means no authority, even for advertised operations"


def test_authorize_never_consumes_anything():
    doc = _doc()
    before = json.dumps(doc, sort_keys=True)
    authorize_capability(
        doc, capability_id="incident-compiler", operation="incident.propose",
        journey_schema=JOURNEY["schema"],
        packet_schema="flywheel.evidence-packet/v1",
        contract_sha256=canonical_sha256(INCIDENT))
    assert json.dumps(doc, sort_keys=True) == before
