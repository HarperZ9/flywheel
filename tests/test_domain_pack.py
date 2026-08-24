"""Domain pack falsifiers: manifest admission, QA honesty, and the
execution lock."""
from pathlib import Path

import pytest

from harness.domain_pack import SCHEMA, run_pack_qa, verify_pack_manifest

FIXTURES = Path(__file__).parent / "fixtures"


def _manifest(**over):
    m = {
        "schema": SCHEMA,
        "pack_id": "pack_physics_basic",
        "version": "1.0.0",
        "domain_id": "physics",
        "claim_types": ["derivation", "measurement"],
        "journey_schema": "flywheel.evidence-journey-projection/v2",
        "packet_schema": "flywheel.evidence-packet/v1",
        "oracle_bindings": [{
            "oracle_id": "kernel_matmul",
            "oracle_version": "1.0",
            "source_sha256": "a" * 64,
            "evidence_kind": "deterministic-kernel",
            "deterministic": True,
        }],
        "fixtures": [
            {"file": "case_correct.json", "expectation": "correct"},
            {"file": "case_incorrect.json", "expectation": "incorrect"},
        ],
        "capabilities": ["data"],
        "containment_class": "unavailable",
        "license": "SPDX:MIT",
        "resource_limits": {"cpu_seconds": 10, "memory_mb": 256,
                            "processes": 1, "output_bytes": 100000,
                            "time_seconds": 30},
        "public_metadata_policy": "public-safe fields only",
        "limitations": ["data admission only"],
        "does_not_prove": "admission is not certification",
        "owner": "maintainers@example.org",
        "review_due_at": "2027-08-22",
    }
    m.update(over)
    return m


def _fixtures_dir(tmp_path: Path) -> Path:
    for name in ("case_correct.json", "case_incorrect.json"):
        (tmp_path / name).write_text("{}", encoding="utf-8")
    return tmp_path


def test_manifest_admits_with_sha_and_state():
    admitted = verify_pack_manifest(_manifest(), fixtures_root=FIXTURES)
    assert admitted["state"] == "data_only"
    assert admitted["pack_sha256"]


def test_executable_pack_locks_without_containment():
    with pytest.raises(ValueError):
        verify_pack_manifest(
            _manifest(capabilities=["data", "executable"]),
            fixtures_root=FIXTURES)


def test_executable_pack_admits_with_containment():
    admitted = verify_pack_manifest(
        _manifest(capabilities=["data", "executable"],
                  containment_class="process_contained"),
        fixtures_root=FIXTURES)
    assert admitted["state"] == "available"


def test_missing_license_owner_or_limits_are_refused():
    for drop in ("license", "owner", "resource_limits"):
        m = {k: v for k, v in _manifest().items() if k != drop}
        with pytest.raises(ValueError):
            verify_pack_manifest(m, fixtures_root=FIXTURES)


def test_non_numeric_limits_are_refused():
    m = _manifest(resource_limits={"cpu_seconds": "lots"})
    with pytest.raises(ValueError):
        verify_pack_manifest(m, fixtures_root=FIXTURES)


def test_network_write_secrets_capabilities_are_never_admitted():
    for cap in ("network", "write", "secrets"):
        with pytest.raises(ValueError):
            verify_pack_manifest(_manifest(capabilities=["data", cap]),
                                 fixtures_root=FIXTURES)


def test_nondeterministic_oracle_is_refused():
    m = _manifest(oracle_bindings=[{
        "oracle_id": "x", "oracle_version": "1", "source_sha256": "a" * 64,
        "evidence_kind": "model", "deterministic": False}])
    with pytest.raises(ValueError):
        verify_pack_manifest(m, fixtures_root=FIXTURES)


def test_secret_or_path_or_command_fields_are_refused():
    with pytest.raises(ValueError):
        verify_pack_manifest(_manifest(owner_secret="x"),
                             fixtures_root=FIXTURES)
    with pytest.raises(ValueError):
        verify_pack_manifest(_manifest(public_metadata_policy={"path": 1}),
                             fixtures_root=FIXTURES)


def test_dynamic_import_or_plugin_discovery_is_refused():
    with pytest.raises(ValueError):
        verify_pack_manifest(
            _manifest(limitations=["uses importlib"]),
            fixtures_root=FIXTURES)


def test_a_missing_fixture_file_is_refused(tmp_path):
    with pytest.raises(ValueError):
        verify_pack_manifest(_manifest(), fixtures_root=tmp_path)


def test_unknown_expectation_is_refused(tmp_path):
    m = _manifest(fixtures=[{"file": "case_correct.json",
                             "expectation": "obviously-fine"}])
    with pytest.raises(ValueError):
        verify_pack_manifest(m, fixtures_root=FIXTURES)


def test_qa_detects_planted_false_accepts_and_reports_denominator():
    m = verify_pack_manifest(_manifest(), fixtures_root=FIXTURES)
    qa = run_pack_qa(m, [
        {"file": "case_correct.json", "observed": "accepted"},
        {"file": "case_incorrect.json", "observed": "refused"},
    ])
    assert qa["denominator"] == 2
    assert qa["detected"] == 1
    assert qa["escaped"] == 0
    assert qa["does_not_prove"]


def test_qa_reports_escaped_false_accepts():
    m = verify_pack_manifest(_manifest(), fixtures_root=FIXTURES)
    qa = run_pack_qa(m, [
        {"file": "case_correct.json", "observed": "accepted"},
        {"file": "case_incorrect.json", "observed": "accepted"},
    ])
    assert qa["escaped"] == 1
    assert qa["resource_usage"] == {"within_limits": False}


def test_qa_counts_platform_skips():
    m = verify_pack_manifest(_manifest(), fixtures_root=FIXTURES)
    qa = run_pack_qa(m, [
        {"file": "case_correct.json", "observed": "skipped"},
        {"file": "case_incorrect.json", "observed": "refused"},
    ])
    assert qa["platform_skips"] == 1
    assert qa["denominator"] == 2


def test_qa_refuses_a_fixture_outside_the_manifest():
    m = verify_pack_manifest(_manifest(), fixtures_root=FIXTURES)
    with pytest.raises(ValueError):
        run_pack_qa(m, [{"file": "stranger.json", "observed": "refused"}])
