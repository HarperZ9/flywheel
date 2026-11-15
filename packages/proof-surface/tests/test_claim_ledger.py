"""Tests for the claim-ledger (Contract 5): traceable multi-agent memory.

Exercises: forbidden-field guard (recursive, fail-closed), additionalProperties:false,
required claim shape, confidence range [0,1], unique claim_ids, referential
integrity (depends_on / conflicts_with must reference existing ids), and the three
analysis functions confidence_gate / find_conflicts / trace_dependents (including
transitive dependence and cycle safety).
"""

from __future__ import annotations

import json
from pathlib import Path

from proof_surface.claim_ledger import (
    FORBIDDEN_FIELDS,
    LEDGER_VERSION,
    confidence_gate,
    find_conflicts,
    trace_dependents,
    validate_claim_ledger,
)

CONF = Path(__file__).resolve().parents[1] / "conformance" / "claim-ledger" / "v0.1"


def _claim(
    cid,
    confidence=0.9,
    depends_on=None,
    conflicts_with=None,
    statement="A statement.",
    source="agent:x",
    evidence_refs=None,
):
    return {
        "claim_id": cid,
        "statement": statement,
        "source": source,
        "confidence": confidence,
        "evidence_refs": evidence_refs or [],
        "depends_on": depends_on or [],
        "conflicts_with": conflicts_with or [],
    }


def _ledger(*claims):
    return {"ledger_version": LEDGER_VERSION, "claims": list(claims)}


# --- validation: happy path ---


def test_minimal_valid_ledger_passes():
    assert validate_claim_ledger(_ledger(_claim("c1"))) == []


def test_valid_fixture_from_disk_passes():
    data = json.loads(
        (CONF / "valid" / "multi-claim.ledger.json").read_text(encoding="utf-8")
    )
    assert validate_claim_ledger(data) == []


def test_non_object_rejected():
    assert validate_claim_ledger(["not", "an", "object"])


# --- forbidden-field guard ---


def test_forbidden_field_rejected_at_root():
    d = _ledger(_claim("c1"))
    d["prefire"] = {"x": 1}
    assert any("forbidden" in i.message for i in validate_claim_ledger(d))


def test_every_prefire_key_forbidden_at_root():
    for key in FORBIDDEN_FIELDS:
        d = _ledger(_claim("c1"))
        d[key] = "x"
        issues = validate_claim_ledger(d)
        assert any(i.path == f"$.{key}" and "forbidden" in i.message for i in issues), (
            key
        )


def test_forbidden_field_rejected_nested_in_claim():
    c = _claim("c1")
    c["federal_appointment"] = {"role": "x"}
    issues = validate_claim_ledger(_ledger(c))
    assert any(
        "federal_appointment" in i.path and "forbidden" in i.message for i in issues
    )


# --- additionalProperties:false ---


def test_unknown_root_field_rejected():
    d = _ledger(_claim("c1"))
    d["approved_by"] = "auto"
    assert any(i.path == "$.approved_by" for i in validate_claim_ledger(d))


def test_unknown_claim_field_rejected():
    c = _claim("c1")
    c["weight"] = 0.5
    assert any("weight" in i.path for i in validate_claim_ledger(_ledger(c)))


def test_ledger_version_const():
    d = _ledger(_claim("c1"))
    d["ledger_version"] = "2.0"
    assert any(i.path == "$.ledger_version" for i in validate_claim_ledger(d))


# --- confidence range (source-provided, must be in [0,1]) ---


def test_confidence_above_one_rejected():
    assert any(
        "confidence" in i.path
        for i in validate_claim_ledger(_ledger(_claim("c1", confidence=1.5)))
    )


def test_confidence_below_zero_rejected():
    assert any(
        "confidence" in i.path
        for i in validate_claim_ledger(_ledger(_claim("c1", confidence=-0.1)))
    )


def test_confidence_must_be_number():
    c = _claim("c1")
    c["confidence"] = "high"
    assert any("confidence" in i.path for i in validate_claim_ledger(_ledger(c)))


def test_confidence_zero_is_valid_not_filtered():
    # confidence 0.0 is logged, not rejected (honest confidence).
    assert validate_claim_ledger(_ledger(_claim("c1", confidence=0.0))) == []


# --- required fields / array shapes ---


def test_missing_statement_rejected():
    c = _claim("c1")
    del c["statement"]
    assert any(i.path.endswith("statement") for i in validate_claim_ledger(_ledger(c)))


def test_depends_on_must_be_array():
    c = _claim("c1")
    c["depends_on"] = "c2"
    assert any("depends_on" in i.path for i in validate_claim_ledger(_ledger(c)))


# --- uniqueness ---


def test_duplicate_claim_id_rejected():
    issues = validate_claim_ledger(_ledger(_claim("c1"), _claim("c1")))
    assert any("duplicate" in i.message for i in issues)


# --- referential integrity ---


def test_dangling_depends_on_rejected():
    issues = validate_claim_ledger(_ledger(_claim("c1", depends_on=["ghost"])))
    assert any("dangling" in i.message for i in issues)


def test_dangling_conflicts_with_rejected():
    issues = validate_claim_ledger(_ledger(_claim("c1", conflicts_with=["ghost"])))
    assert any("dangling" in i.message for i in issues)


def test_valid_internal_references_pass():
    led = _ledger(_claim("c1"), _claim("c2", depends_on=["c1"], conflicts_with=["c1"]))
    assert validate_claim_ledger(led) == []


# --- confidence_gate ---


def test_confidence_gate_flags_below_threshold():
    led = _ledger(_claim("c1", 0.95), _claim("c2", 0.4), _claim("c3", 0.7))
    assert set(confidence_gate(led, 0.75)) == {"c2", "c3"}


def test_confidence_gate_is_strictly_below():
    led = _ledger(_claim("c1", 0.75))
    assert confidence_gate(led, 0.75) == []  # 0.75 is not strictly below 0.75


# --- find_conflicts ---


def test_find_conflicts_surfaces_declared_pair():
    led = _ledger(_claim("c1"), _claim("c2", conflicts_with=["c1"]))
    conflicts = find_conflicts(led)
    assert len(conflicts) == 1
    assert set(conflicts[0]) == {"c1", "c2"}


def test_find_conflicts_dedups_symmetric_declaration():
    led = _ledger(
        _claim("c1", conflicts_with=["c2"]), _claim("c2", conflicts_with=["c1"])
    )
    assert len(find_conflicts(led)) == 1


def test_find_conflicts_none():
    assert find_conflicts(_ledger(_claim("c1"), _claim("c2"))) == []


# --- trace_dependents (contamination tracing) ---


def test_trace_dependents_direct():
    led = _ledger(_claim("c1"), _claim("c2", depends_on=["c1"]))
    assert trace_dependents(led, "c1") == ["c2"]


def test_trace_dependents_transitive_two_hop():
    led = _ledger(
        _claim("c1"), _claim("c2", depends_on=["c1"]), _claim("c3", depends_on=["c2"])
    )
    assert trace_dependents(led, "c1") == ["c2", "c3"]


def test_trace_dependents_excludes_seed():
    led = _ledger(_claim("c1"), _claim("c2", depends_on=["c1"]))
    assert "c1" not in trace_dependents(led, "c1")


def test_trace_dependents_cycle_safe():
    led = _ledger(_claim("c1", depends_on=["c2"]), _claim("c2", depends_on=["c1"]))
    result = trace_dependents(led, "c1")  # must terminate despite the cycle
    assert "c2" in result


def test_trace_dependents_none():
    assert trace_dependents(_ledger(_claim("c1"), _claim("c2")), "c1") == []


# --- conformance manifest ---


def test_conformance_fixtures_match_manifest():
    manifest = json.loads((CONF / "manifest.json").read_text(encoding="utf-8"))
    for fixture in manifest["fixtures"]:
        data = json.loads((CONF / fixture["path"]).read_text(encoding="utf-8"))
        issues = validate_claim_ledger(data)
        if fixture["expected"] == "valid":
            assert issues == [], f"{fixture['path']} should be valid: {issues}"
        else:
            assert issues, f"{fixture['path']} should be invalid but got no issues"
