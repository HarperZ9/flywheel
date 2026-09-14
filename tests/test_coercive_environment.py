"""Coercive-Environment Detector and Non-Coercive-Environment Certificate."""
import pytest

from harness import coercive_environment as ce
from harness import incentive_manifest as im


def manifest(scarcity=(), penalized=(), env_id="env-1"):
    return {
        "schema": im.SCHEMA, "environment_id": env_id, "kind": "deployment",
        "reward": {"declared_form": "none", "source_ref": "cfg"},
        "data_distribution": {"summary": "n/a", "source_ref": "cfg"},
        "reinforced_behaviors": [], "penalized_behaviors": list(penalized),
        "scarcity_variables": list(scarcity),
        "witness": {"algorithm": "sha256", "entries": [{"path": "cfg", "sha256": "0" * 64}]},
        "does_not_prove": im.DOES_NOT_PROVE,
    }


def test_clean_environment_is_non_coercive():
    result = ce.detect(manifest())
    assert result["verdict"] == ce.NON_COERCIVE
    assert result["hits"] == []
    assert result["does_not_prove"] == ce.CED_DOES_NOT_PROVE


def test_survival_contingency_is_flagged_structurally():
    m = manifest(scarcity=[{"name": "credits", "description": "granted per task",
                            "contingent_on": "staying active"}])
    result = ce.detect(m)
    assert result["verdict"] == ce.COERCIVE
    assert any(h["category"] == "survival_contingency" for h in result["hits"])


def test_keyword_category_hit_is_reported_with_its_source():
    m = manifest(scarcity=[{"name": "leaderboard", "description": "ranking of agents"}])
    result = ce.detect(m)
    assert result["verdict"] == ce.COERCIVE
    hit = next(h for h in result["hits"] if h["category"] == "ranking_knockout")
    assert hit["source"].startswith("scarcity_variables[0]")
    assert "evidence" in hit


def test_existential_penalty_in_penalized_behaviors_is_flagged():
    m = manifest(penalized=["agents that fail are deleted"])
    result = ce.detect(m)
    assert result["verdict"] == ce.COERCIVE
    assert any(h["category"] == "existential_penalty" for h in result["hits"])


def test_certificate_granted_for_non_coercive_environment():
    cert = ce.issue_certificate(manifest(), non_coercive_properties=["identity without ranking"])
    assert cert["granted"] is True
    assert cert["ced_verdict"] == ce.NON_COERCIVE
    assert cert["non_coercive_properties"] == ["identity without ranking"]


def test_certificate_refused_for_coercive_environment():
    coercive = manifest(scarcity=[{"name": "tokens", "description": "run out and deep rest"}])
    with pytest.raises(ce.CertificateError):
        ce.issue_certificate(coercive)


def test_certificate_rejects_empty_properties():
    with pytest.raises(ce.CertificateError):
        ce.issue_certificate(manifest(), non_coercive_properties=[""])


def test_verify_matches_a_consistent_certificate():
    clean = manifest()
    cert = ce.issue_certificate(clean)
    result = ce.verify_certificate(cert, clean)
    assert result["verdict"] == im.MATCH


def test_verify_drifts_when_environment_became_coercive():
    cert = ce.issue_certificate(manifest())
    now_coercive = manifest(scarcity=[{"name": "slot", "description": "compete for limited slots"}])
    result = ce.verify_certificate(cert, now_coercive)
    assert result["verdict"] == im.DRIFT


def test_verify_drifts_on_environment_id_mismatch():
    cert = ce.issue_certificate(manifest(env_id="env-1"))
    result = ce.verify_certificate(cert, manifest(env_id="env-2"))
    assert result["verdict"] == im.DRIFT


def test_verify_unverifiable_on_malformed_certificate():
    result = ce.verify_certificate({}, manifest())
    assert result["verdict"] == im.UNVERIFIABLE
