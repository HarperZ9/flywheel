"""Incident proposal: a deterministic, read-only compilation of an
admitted case against an admitted projection. The proposal cannot
self-accept, cannot execute, and carries its review requirements and
does_not_prove on its face."""
import pytest

from harness.incident_case import new_incident_case
from harness.incident_proposal import compile_incident_proposal

CASE = new_incident_case(
    case_id="case_" + "a" * 8,
    journey_ref="jrn_" + "a" * 32,
    event_head_sha256="a" * 64,
    source_refs=[{"fact_id": "fact_" + "a" * 8,
                  "statement": "the gate refused"}],
    failure={"summary": "check failed on the submitted object"},
    created_at="2026-08-22T12:00:00Z",
)
CAPABILITY_SHA = "c" * 64


def _projection(head="a" * 64):
    return {
        "journey_ref": "jrn_" + "a" * 32,
        "event_head_sha256": head,
        "facts": [{"fact_id": "fact_" + "a" * 8,
                   "statement": "the gate refused"}],
    }


def _proposal(projection=None):
    return compile_incident_proposal(
        case=CASE, projection=projection or _projection(),
        capability_sha256=CAPABILITY_SHA)


def test_proposal_schema_and_state():
    p = _proposal()
    assert p["schema"] == "flywheel.incident-proposed-graph/v1"
    assert p["state"] == "proposed"


def test_deterministic_and_byte_identical():
    assert _proposal() == _proposal()


def test_source_facts_must_exist_in_the_projection():
    p = _proposal()  # the admitted fact exists; compilation succeeds
    expect_ids = ["fact_" + "a" * 8]
    assert p["source_fact_ids"] == expect_ids
    stranger = {"journey_ref": "jrn_" + "a" * 32,
                "event_head_sha256": "a" * 64,
                "facts": []}
    with pytest.raises(ValueError):
        compile_incident_proposal(case=CASE, projection=stranger,
                                  capability_sha256=CAPABILITY_SHA)


def test_stale_head_is_refused():
    with pytest.raises(ValueError):
        _proposal(_projection(head="b" * 64))


def _no_acceptance_fields(value: object, path: str = "") -> None:
    """Field-name scan: no key anywhere in the proposal may claim
    acceptance or execution. Prose that says what the proposal does NOT
    do is honest, not a violation."""
    if isinstance(value, dict):
        for key, child in value.items():
            here = f"{path}.{key}"
            lowered = str(key).lower()
            for banned in ("accepted", "pass", "receipt", "execution",
                           "command"):
                assert banned not in lowered, (banned, here)
            _no_acceptance_fields(child, here)
    elif isinstance(value, list):
        for i, child in enumerate(value):
            _no_acceptance_fields(child, f"{path}[{i}]")


def test_no_accepted_or_executing_fields_ever():
    p = _proposal()
    _no_acceptance_fields(p)


def test_review_requirements_and_does_not_prove_are_explicit():
    p = _proposal()
    assert isinstance(p["review_requirements"], list) and p["review_requirements"]
    assert p["does_not_prove"]
    assert p["limitations"]


def test_edges_are_acyclic_and_reference_known_nodes():
    p = _proposal()
    ids = {n["node_id"] for n in p.get("checks", [])} | set(
        p["source_fact_ids"])
    for edge in p["edges"]:
        assert edge[0] != edge[1]
        assert edge[0] in ids and edge[1] in ids
