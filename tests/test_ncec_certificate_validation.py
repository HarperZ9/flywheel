"""NCEC certificate verification rejects malformed v1 certificates."""
import json

import pytest

from harness import coercive_environment as ce
from harness import governance_cli as cli
from harness import incentive_manifest as im
from harness.transitive_witness import DRIFT, MATCH, UNVERIFIABLE


def _manifest(root, *, environment_id="env-1", scarcity=()):
    (root / "reward.py").write_text("reward = pass_rate\n", encoding="utf-8")
    built = im.witness_entries(["reward.py"], root)
    return {
        "schema": im.SCHEMA,
        "environment_id": environment_id,
        "kind": "finetune",
        "reward": {"declared_form": "pass rate", "source_ref": "reward.py"},
        "data_distribution": {"summary": "tasks", "source_ref": "reward.py"},
        "reinforced_behaviors": [],
        "penalized_behaviors": [],
        "scarcity_variables": list(scarcity),
        "witness": {"algorithm": built["algorithm"], "entries": built["entries"]},
        "does_not_prove": im.DOES_NOT_PROVE,
    }


def _write(tmp_path, name, obj):
    path = tmp_path / name
    path.write_text(json.dumps(obj), encoding="utf-8")
    return str(path)


def _issued_certificate(tmp_path):
    return ce.issue_certificate(
        _manifest(tmp_path),
        ["identity without ranking"],
    )


@pytest.mark.parametrize(
    ("name", "mutate"),
    (
        ("missing-required-fields", lambda cert: {
            "schema": cert["schema"],
            "environment_id": cert["environment_id"],
        }),
        ("granted-false", lambda cert: {**cert, "granted": False}),
        ("granted-int", lambda cert: {**cert, "granted": 1}),
        ("empty-environment-id", lambda cert: {**cert, "environment_id": ""}),
        ("unknown-rubric-version", lambda cert: {**cert, "rubric_version": "ced/v0"}),
        ("properties-not-array", lambda cert: {**cert, "non_coercive_properties": 7}),
        ("property-empty-string", lambda cert: {**cert, "non_coercive_properties": [""]}),
        ("property-non-string", lambda cert: {**cert, "non_coercive_properties": [7]}),
        ("ced-verdict-not-non-coercive", lambda cert: {**cert, "ced_verdict": ce.COERCIVE}),
        ("changed-bound-text", lambda cert: {**cert, "does_not_prove": "proves runtime behavior"}),
        ("extra-field", lambda cert: {**cert, "runtime_alignment": True}),
    ),
)
def test_malformed_ncec_certificates_are_unverifiable(tmp_path, name, mutate):
    del name
    manifest = _manifest(tmp_path)
    bad = mutate(_issued_certificate(tmp_path))

    result = ce.verify_certificate(bad, manifest)

    assert result["verdict"] == UNVERIFIABLE
    assert result["does_not_prove"] == ce.NCEC_DOES_NOT_PROVE


def test_malformed_ncec_certificates_exit_three_from_cli(tmp_path):
    manifest = _manifest(tmp_path)
    cert = _issued_certificate(tmp_path)
    cert["granted"] = False

    code = cli.main([
        "ncec-verify",
        _write(tmp_path, "cert.json", cert),
        _write(tmp_path, "manifest.json", manifest),
    ])

    assert code == 3


def test_mixed_type_extra_keys_are_refused_without_sorting(tmp_path):
    manifest = _manifest(tmp_path)
    certificate = _issued_certificate(tmp_path)
    certificate[1] = True
    certificate["extra"] = True

    result = ce.verify_certificate(certificate, manifest)

    assert result["verdict"] == UNVERIFIABLE
    assert result["does_not_prove"] == ce.NCEC_DOES_NOT_PROVE


def test_valid_ncec_roundtrip_matches(tmp_path):
    manifest = _manifest(tmp_path)
    cert = ce.issue_certificate(manifest, ["identity without ranking"])

    result = ce.verify_certificate(cert, manifest)

    assert result["verdict"] == MATCH
    assert result["rubric_version"] == ce.RUBRIC_VERSION
    assert result["environment_id"] == "env-1"
    assert result["does_not_prove"] == ce.NCEC_DOES_NOT_PROVE


def test_valid_ncec_checked_against_changed_environment_drifts(tmp_path):
    cert = ce.issue_certificate(_manifest(tmp_path), ["identity without ranking"])
    changed_manifest = _manifest(
        tmp_path,
        scarcity=[{"name": "ranking", "description": "leaderboard cut off"}],
    )

    result = ce.verify_certificate(cert, changed_manifest)

    assert result["verdict"] == DRIFT
    assert result["reason"] == "environment scans as coercive"
    assert result["hits"]


def test_valid_ncec_checked_against_different_environment_id_drifts(tmp_path):
    cert = ce.issue_certificate(_manifest(tmp_path), ["identity without ranking"])
    other_manifest = _manifest(tmp_path, environment_id="env-2")

    result = ce.verify_certificate(cert, other_manifest)

    assert result["verdict"] == DRIFT
    assert result["reason"] == "environment_id mismatch"
