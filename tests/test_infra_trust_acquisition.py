"""Tests for the trust model and acquisition manifest (Family 6)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.infra.acquisition import (
    SCHEMA as ACQ_SCHEMA,
    build_manifest,
    recheck_hash,
    verify_manifest,
)
from harness.infra.trust_model import (
    SCHEMA as TM_SCHEMA,
    Component,
    SafetyClaim,
    TrustModel,
    default_flywheel_trust_model,
)


# --- trust model ----------------------------------------------------------


def test_trust_model_has_schema():
    model = TrustModel(model_id="test")
    assert model.to_dict()["schema"] == TM_SCHEMA


def test_add_component_validates_type():
    model = TrustModel(model_id="test")
    model.add_component(name="gate1", component_type="gate", owner="alice")
    with pytest.raises(ValueError, match="component_type"):
        model.add_component(name="bad", component_type="bogus", owner="x")


def test_validate_passes_for_complete_model():
    model = TrustModel(model_id="test")
    model.add_component(name="gate", component_type="gate", owner="alice")
    model.add_claim(
        claim_id="C1", statement="writes denied",
        enforcement_component="gate", owner="alice")
    assert model.validate() == []


def test_validate_catches_missing_enforcement_component():
    model = TrustModel(model_id="test")
    model.add_component(name="gate", component_type="gate", owner="alice")
    model.add_claim(
        claim_id="C1", statement="writes denied",
        enforcement_component="nonexistent", owner="alice")
    issues = model.validate()
    assert any("not in components" in i for i in issues)


def test_validate_catches_claim_without_owner():
    model = TrustModel(model_id="test")
    model.add_component(name="gate", component_type="gate", owner="alice")
    model.add_claim(
        claim_id="C1", statement="writes denied",
        enforcement_component="gate", owner="")
    issues = model.validate()
    assert any("no owner" in i for i in issues)


def test_find_single_points_of_failure():
    model = TrustModel(model_id="test")
    model.add_component(name="gate", component_type="gate", owner="alice")
    model.add_component(name="monitor", component_type="monitor", owner="bob")
    model.add_claim(
        claim_id="C1", statement="x",
        enforcement_component="gate", owner="alice")
    model.add_claim(
        claim_id="C2", statement="y",
        enforcement_component="monitor", owner="bob")
    spofs = model.find_single_points_of_failure()
    # Both are sole enforcers of their claims
    assert "gate" in spofs
    assert "monitor" in spofs


def test_default_flywheel_trust_model_validates():
    model = default_flywheel_trust_model()
    assert model.validate() == []
    assert len(model.components) >= 5
    assert len(model.safety_claims) >= 4
    assert len(model.single_points_of_failure) > 0  # honest about SPOFs


def test_default_model_names_adversary_paths():
    model = default_flywheel_trust_model()
    assert any("network egress" in p for p in model.adversary_paths)
    assert any("network monitor" in p for p in model.adversary_paths)


def test_trust_model_propagates_complete_governance_references():
    model = TrustModel(
        model_id="governed", tadr_tier="T2", tadr_modifiers=["A"],
        classification_ref="a" * 64, governance_verdict="pause",
        pause_triggers=["capability-increase"], control_digest="b" * 64)
    assert model.to_dict()["governance"] == {
        "tadr_tier": "T2", "tadr_modifiers": ["A"],
        "classification_ref": "a" * 64, "governance_verdict": "pause",
        "pause_triggers": ["capability-increase"],
        "control_digest": "b" * 64,
    }


def test_trust_model_rejects_invalid_governance_values():
    with pytest.raises(ValueError, match="tadr_tier"):
        TrustModel(model_id="bad", tadr_tier="T9")


def test_trust_model_revalidates_mutated_governance():
    model = TrustModel(model_id="bad-later")
    model.tadr_tier = "T9"
    with pytest.raises(ValueError, match="tadr_tier"):
        model.to_dict()


# --- acquisition manifest -------------------------------------------------


def test_build_manifest_creates_sealed_object(tmp_path: Path):
    evidence = tmp_path / "log.txt"
    content = b"important evidence\n"
    evidence.write_bytes(content)
    m = build_manifest(
        source_path=str(evidence),
        collector="analyst-alice",
        authorization="IR-2026-001",
    )
    assert m["schema"] == ACQ_SCHEMA
    assert m["acquisition_id"].startswith("acq-")
    assert len(m["seal"]) == 64
    assert m["source"]["sha256"] != ""
    assert m["source"]["byte_count"] == len(content)
    assert m["collector"] == "analyst-alice"


def test_build_manifest_raises_on_missing_source():
    with pytest.raises(FileNotFoundError):
        build_manifest(source_path="/nonexistent/path", collector="x")


def test_verify_manifest_match(tmp_path: Path):
    evidence = tmp_path / "log.txt"
    evidence.write_text("evidence", encoding="utf-8")
    m = build_manifest(source_path=str(evidence), collector="alice")
    v = verify_manifest(m)
    assert v["verdict"] == "MATCH"


def test_verify_manifest_tampered(tmp_path: Path):
    evidence = tmp_path / "log.txt"
    evidence.write_text("evidence", encoding="utf-8")
    m = build_manifest(source_path=str(evidence), collector="alice")
    m["collector"] = "attacker"  # tamper
    v = verify_manifest(m)
    assert v["verdict"] == "TAMPERED"


def test_verify_manifest_bad_schema():
    v = verify_manifest({"schema": "wrong"})
    assert v["verdict"] == "UNVERIFIABLE"


def test_recheck_hash_match(tmp_path: Path):
    evidence = tmp_path / "log.txt"
    evidence.write_text("unchanged", encoding="utf-8")
    m = build_manifest(source_path=str(evidence), collector="alice")
    r = recheck_hash(m)
    assert r["verdict"] == "MATCH"


def test_recheck_hash_drift(tmp_path: Path):
    evidence = tmp_path / "log.txt"
    evidence.write_text("original", encoding="utf-8")
    m = build_manifest(source_path=str(evidence), collector="alice")
    evidence.write_text("tampered", encoding="utf-8")  # change after manifest
    r = recheck_hash(m)
    assert r["verdict"] == "DRIFT"


def test_recheck_hash_source_gone(tmp_path: Path):
    evidence = tmp_path / "log.txt"
    evidence.write_text("gone soon", encoding="utf-8")
    m = build_manifest(source_path=str(evidence), collector="alice")
    evidence.unlink()
    r = recheck_hash(m)
    assert r["verdict"] == "UNVERIFIABLE"


def test_manifest_round_trips_json(tmp_path: Path):
    evidence = tmp_path / "data.bin"
    evidence.write_bytes(b"\x00\x01\x02\x03")
    m = build_manifest(source_path=str(evidence), collector="bob")
    # serialize and deserialize
    js = json.dumps(m)
    m2 = json.loads(js)
    v = verify_manifest(m2)
    assert v["verdict"] == "MATCH"
