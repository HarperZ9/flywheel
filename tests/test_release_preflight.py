"""Release preflight: the identity exists only when every blocking fact
is resolved, the versions agree across tag/Python/Dart surfaces, and the
profile is the non-executing v1 profile, never called sandboxed."""
from pathlib import Path

import pytest

from harness.release_identity import (
    PROFILE,
    build_release_identity,
)

RECEIPTS = ["a" * 64] * 5


def _policies(root: Path, **over):
    release = root / "desktop" / "release"
    release.mkdir(parents=True, exist_ok=True)
    support = {
        "blocked": [],
        "editions": "Windows 11 23H2 x64",
        "architectures": ["x64"],
        "clean_runner_label": "self-hosted,windows,flywheel-clean-vm",
        "previous_signed_installer": "sha256:" + "b" * 64,
    }
    toolchains = {
        "blocked": [],
        "python": "3.12", "flutter": "3.44.6", "dart": "3.6+",
        "pyinstaller": "6.21.0", "inno_setup": "6",
        "runner_images": "digest-pinned",
    }
    policy = {
        "blocked": [],
        "profile": PROFILE,
        "desktop_product_id": "{8A6E3B71-1111-4C6C-9A2F-111111111111}",
        "installer_app_id": "{8A6E3B71-2222-4C6C-9A2F-222222222222}",
        "api_schema": "flywheel.evidence-journey-projection/v2",
        "authenticode_provider": "accepted-provider",
        "timestamp_url": "http://timestamp.example/rfc3161",
        "retention_days": 90,
        "denied_operations": ["agent_exec"],
    }
    payload = {
        "blocked": [],
        "allow": [], "reject_globs": True, "reject_symlinks": True,
        "reject_alternate_data_streams": True, "reject_case_collisions": True,
        "reject_reserved_names": True,
        "font_provenance": "accepted: all fonts licensed",
        "third_party_notices": "accepted: complete",
    }
    for name, doc in (("windows-support.json", support),
                      ("toolchains.json", toolchains),
                      ("release-policy.json", policy),
                      ("payload-policy.json", payload)):
        doc.update(over.get(name, {}))
        (release / name).write_text(
            __import__("json").dumps(doc), encoding="utf-8")
    (root / "desktop" / "pubspec.yaml").write_text(
        "version: 0.3.10+10\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        'version = "0.3.10"\n', encoding="utf-8")


def _identity(root):
    return build_release_identity(
        root, tag="v0.3.10", source_commit="a" * 40,
        phase_receipts=RECEIPTS)


def test_a_complete_preflight_binds_one_identity(tmp_path):
    _policies(tmp_path)
    identity = _identity(tmp_path)
    assert identity["schema"] == "flywheel.release-identity/v1"
    assert identity["version"] == "0.3.10"
    assert identity["profile"] == PROFILE
    assert identity["wheel_name"] == (
        "flywheel_verify-0.3.10-py3-none-any.whl")
    assert len(identity["policy_sha256"]) == 64


def test_any_blocked_fact_stops_the_identity(tmp_path):
    _policies(tmp_path)
    support = tmp_path / "desktop" / "release" / "windows-support.json"
    support.write_text(
        __import__("json").dumps({
            "blocked": ["clean_snapshot_runner"],
            "editions": "BLOCKED",
        }),
        encoding="utf-8")
    with pytest.raises(ValueError) as e:
        _identity(tmp_path)
    assert "blocking facts" in str(e.value)
    assert "clean_snapshot_runner" in str(e.value)


def test_version_drift_refuses_the_identity(tmp_path):
    _policies(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        'version = "0.3.9"\n', encoding="utf-8")
    with pytest.raises(ValueError) as e:
        _identity(tmp_path)
    assert "drift" in str(e.value)


def test_wrong_receipt_count_or_shape_is_refused(tmp_path):
    _policies(tmp_path)
    with pytest.raises(ValueError):
        build_release_identity(tmp_path, tag="v0.3.10",
                               source_commit="a" * 40,
                               phase_receipts=["a" * 64] * 4)
    with pytest.raises(ValueError):
        build_release_identity(tmp_path, tag="v0.3.10",
                               source_commit="a" * 40,
                               phase_receipts=["short"] * 5)


def test_the_profile_is_never_called_sandboxed(tmp_path):
    _policies(tmp_path, **{"release-policy.json": {
        "profile": PROFILE, "note": "this profile is sandboxed"}})
    with pytest.raises(ValueError) as e:
        _identity(tmp_path)
    assert "sandbox" in str(e.value)


def test_missing_policy_files_are_typed_failures(tmp_path):
    (tmp_path / "desktop").mkdir()
    with pytest.raises(ValueError) as e:
        _identity(tmp_path)
    assert "missing preflight fact" in str(e.value)
