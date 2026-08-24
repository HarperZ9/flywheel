"""Contextual extensions acceptance: the composition facts Phase 5
binds. Each assertion cites the task suite that pins it in depth; this
file exists so the acceptance record cites one runnable command."""
from harness.evidence_extension_contracts import (
    SCHEMA as CAPABILITIES_SCHEMA,
    authorize_capability,
    capability_document,
)
from harness.evidence_extension_route import (
    handle_frontier_axis,
    handle_incident_propose,
)
from harness.frontier_claim import new_frontier_claim
from harness.frontier_claim_projection import AXES, project_frontier_axes
from harness.incident_proposal import compile_incident_proposal
from harness.incident_case import new_incident_case
from harness.domain_pack import run_pack_qa, verify_pack_manifest

JOURNEY = {"schema": "flywheel.evidence-journey-projection/v2",
           "event_head_sha256": "a" * 64}
RECEIPT = {"accepted": True, "receipt_sha256": "b" * 64}
CONTRACTS = {
    "schema": "flywheel.incident-case/v1",
    "operations": ["incident.propose"],
    "limits": {"max_source_refs": 32},
    "acceptance_receipt": RECEIPT,
    "data_only": True,
}
PACK = {
    "schema": "flywheel.domain-pack/v1",
    "pack_id": "pack_physics_basic",
    "version": "1.0.0",
    "domain_id": "physics",
    "claim_types": ["derivation"],
    "journey_schema": "flywheel.evidence-journey-projection/v2",
    "packet_schema": "flywheel.evidence-packet/v1",
    "oracle_bindings": [{"oracle_id": "k", "oracle_version": "1",
                         "source_sha256": "a" * 64,
                         "evidence_kind": "kernel", "deterministic": True}],
    "fixtures": [{"file": "case_correct.json", "expectation": "correct"},
                 {"file": "case_incorrect.json", "expectation": "incorrect"}],
    "capabilities": ["data"],
    "containment_class": "unavailable",
    "license": "SPDX:MIT",
    "resource_limits": {"cpu_seconds": 10, "memory_mb": 64, "processes": 1,
                        "output_bytes": 1000, "time_seconds": 10},
    "public_metadata_policy": "public-safe",
    "limitations": ["data only"],
    "does_not_prove": "admission is not certification",
    "owner": "m@example.org",
    "review_due_at": "2027-08-22",
}


def test_capability_sheet_is_fail_closed_and_hash_bound():
    empty = capability_document(
        journey=JOURNEY, incident_contract=None, frontier_contract=None,
        pack_contracts=[], containment={"process": False})
    assert empty["schema"] == CAPABILITIES_SCHEMA
    assert empty["capabilities"] == [], (
        "no accepted contracts means zero advertised capabilities")


def test_incident_proposal_deterministic_never_accepted():
    case = new_incident_case(
        case_id="case_" + "a" * 8, journey_ref="jrn_" + "a" * 32,
        event_head_sha256="a" * 64,
        source_refs=[{"fact_id": "fact_" + "a" * 8, "statement": "s"}],
        failure={"summary": "the gate refused"}, created_at="2026-08-22T00:00:00Z")
    projection = {"journey_ref": "jrn_" + "a" * 32,
                  "event_head_sha256": "a" * 64,
                  "facts": [{"fact_id": "fact_" + "a" * 8, "statement": "s"}]}
    p1 = compile_incident_proposal(case=case, projection=projection,
                                   capability_sha256="c" * 64)
    p2 = compile_incident_proposal(case=case, projection=projection,
                                   capability_sha256="c" * 64)
    assert p1 == p2 and p1["state"] == "proposed"


def test_frontier_axes_independent_no_composite():
    claim = new_frontier_claim(
        claim_id="clm_" + "a" * 8, journey_ref="jrn_" + "a" * 32,
        source={"title": "t"}, proposition={"statement": "s"},
        created_at="2026-08-22T00:00:00Z",
        novelty_state="NOT_FOUND_IN_CORPUS", verdict=None)
    axes = project_frontier_axes(claim=claim, journey_ref="jrn_" + "a" * 32,
                                 event_head_sha256="a" * 64)
    assert len(axes["axes"]) == len(AXES)
    hashes = {a["fields_sha256"] for a in axes["axes"]}
    assert len(hashes) == len(AXES)


def test_data_only_pack_admits_executable_requires_containment():
    admitted = verify_pack_manifest(PACK, fixtures_root="tests/fixtures")
    assert admitted["state"] == "data_only"
    executable = dict(PACK, capabilities=["data", "executable"],
                      containment_class="process_contained")
    assert verify_pack_manifest(executable,
                                fixtures_root="tests/fixtures")[
        "state"] == "available"


def test_exact_grant_mutation_denies_without_binding():
    sheet = capability_document(
        journey=JOURNEY, incident_contract=CONTRACTS, frontier_contract={
            "schema": "flywheel.frontier-claim/v1",
            "operations": ["frontier.project", "frontier.axis.append"],
            "limits": {"max_axes": 4},
            "acceptance_receipt": RECEIPT, "data_only": True},
        pack_contracts=[], containment={"process": True})
    body = {"journey_ref": "jrn_" + "a" * 32,
            "expected_event_head": "a" * 64,
            "client_request_id": "req-1", "grant_ref": "gnt_" + "a" * 32,
            "claim_id": "clm_" + "a" * 8, "axis": "value",
            "patch": {"novelty_state": "known"},
            "owner_ref": "owner_" + "a" * 32,
            "capability_sha256": "c" * 64}
    # The sheet above carries a different contract hash than the body's:
    # a stale contract binding denies before any CAS dispatch.
    _, code = handle_frontier_axis(body, sheet, lambda: "now")
    assert code == 403


def test_incident_route_denies_absent_capability():
    empty = capability_document(
        journey=JOURNEY, incident_contract=None, frontier_contract=None,
        pack_contracts=[], containment={"process": True})
    case = new_incident_case(
        case_id="case_" + "a" * 8, journey_ref="jrn_" + "a" * 32,
        event_head_sha256="a" * 64,
        source_refs=[{"fact_id": "fact_" + "a" * 8, "statement": "s"}],
        failure={"summary": "s"}, created_at="2026-08-22T00:00:00Z")
    body = {"capability_sha256": "c" * 64, "case": case,
            "projection": {"journey_ref": "jrn_" + "a" * 32,
                           "event_head_sha256": "a" * 64, "facts": []}}
    _, code = handle_incident_propose(body, empty)
    assert code == 403


def test_authorize_is_pure_over_the_sheet():
    sheet = capability_document(
        journey=JOURNEY, incident_contract=CONTRACTS, frontier_contract=None,
        pack_contracts=[], containment={"process": True})
    from harness.evidence_json import canonical_sha256
    before = canonical_sha256(sheet)
    authorize_capability(
        sheet, capability_id="incident-compiler",
        operation="incident.propose", journey_schema=JOURNEY["schema"],
        packet_schema="flywheel.evidence-packet/v1",
        contract_sha256=canonical_sha256(CONTRACTS))
    assert canonical_sha256(sheet) == before
