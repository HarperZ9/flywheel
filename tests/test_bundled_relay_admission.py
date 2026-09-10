import hashlib
import json
from types import SimpleNamespace

import pytest

from harness.evidence_json import canonical_sha256


RELAY_COMMIT = "81d544bd5f7435fc65f16a81d3f369818e493ddf"
SOURCE_DIGEST = "sha256:" + "1" * 64
DESCRIPTOR_DIGEST = "sha256:" + "2" * 64


def _descriptor(*, version="0.2.0", source_digest=SOURCE_DIGEST):
    files = [{
        "path": "src/relay/local_mcp.py",
        "bytes": 12,
        "sha256": "sha256:" + hashlib.sha256(b"relay status").hexdigest(),
    }]
    return {
        "schema": "flywheel.bundled-lane-component/v1",
        "name": "relay",
        "version": version,
        "source": {
            "repo": "https://github.com/HarperZ9/relay",
            "commit": RELAY_COMMIT,
            "path": "src/relay",
            "algorithm": "sha256-canonical-source-manifest/v1",
            "file_count": 1,
            "bytes": 12,
            "files": files,
            "manifest_sha256": source_digest,
        },
        "entrypoint": {
            "argv": ["--bundled-lane-mcp", "relay"],
            "module": "relay.local_mcp",
            "callable": "serve",
            "health_tool": "relay.status",
        },
        "does_not_prove": [
            "NOT_PROVES_REPLACEMENT_OF_TRUSTED_EXECUTABLE: the descriptor binds the reviewed Relay source included in this build, not a later replacement of the whole gateway executable.",
            "NOT_PROVES_AGENTIC_TASK_SUCCESS: relay.status is an identity and transport check, not proof that Relay can complete model-backed work.",
            "NOT_PROVES_PROVIDER_OR_NETWORK_READINESS: the status check is network-free and carries no provider credential custody.",
        ],
    }


def _write_descriptor(tmp_path, descriptor):
    path = tmp_path / "relay.json"
    path.write_text(json.dumps(descriptor), encoding="utf-8")
    return path


def _expected(descriptor):
    return {
        "descriptor_sha256": "sha256:" + canonical_sha256(descriptor),
        "source_manifest_sha256": descriptor["source"]["manifest_sha256"],
        "source_commit": RELAY_COMMIT,
        "version": "0.2.0",
        "module": "relay.local_mcp",
        "callable": "serve",
        "health_tool": "relay.status",
    }


def test_valid_descriptor_admits_only_relay_status(tmp_path):
    """Catches admission through PATH, registry python, or unbounded tools."""
    from harness.bundled_lane_admission import admit_bundled_lane

    descriptor = _descriptor(source_digest="sha256:" + canonical_sha256(
        _descriptor()["source"]["files"]))
    path = _write_descriptor(tmp_path, descriptor)

    result = admit_bundled_lane(
        "relay", executable="D:/app/flywheel-gateway.exe", environ={},
        descriptor_path=path, importable_fn=lambda name: name == "relay.local_mcp",
        expected=_expected(descriptor),
    )

    assert result.blocking_codes == ()
    assert result.launch.argv == (
        "D:/app/flywheel-gateway.exe", "--bundled-lane-mcp", "relay")
    assert result.launch.allowed_tools == ("relay.status",)
    assert result.launch.inherit_env is False
    assert result.launch.hide_window is True
    assert result.component["descriptor_sha256"] == _expected(descriptor)["descriptor_sha256"]
    assert result.component["source_commit"] == RELAY_COMMIT


def test_descriptor_absent_or_tampered_leaves_relay_missing(tmp_path):
    """Catches trusting a missing or mutated descriptor as its own authority."""
    from harness.bundled_lane_admission import admit_bundled_lane

    missing = admit_bundled_lane(
        "relay", executable="gateway.exe", environ={},
        descriptor_path=tmp_path / "missing.json",
        importable_fn=lambda _name: True,
        expected={"descriptor_sha256": DESCRIPTOR_DIGEST,
                  "source_manifest_sha256": SOURCE_DIGEST,
                  "source_commit": RELAY_COMMIT, "version": "0.2.0",
                  "module": "relay.local_mcp", "callable": "serve",
                  "health_tool": "relay.status"},
    )
    assert missing.launch is None
    assert "bundled_descriptor_missing" in missing.blocking_codes

    descriptor = _descriptor(source_digest="sha256:" + canonical_sha256(
        _descriptor()["source"]["files"]))
    tampered_path = _write_descriptor(tmp_path, descriptor)
    tampered = admit_bundled_lane(
        "relay", executable="gateway.exe", environ={},
        descriptor_path=tampered_path, importable_fn=lambda _name: True,
        expected={**_expected(descriptor),
                  "descriptor_sha256": DESCRIPTOR_DIGEST},
    )
    assert tampered.launch is None
    assert "bundled_descriptor_digest_mismatch" in tampered.blocking_codes


def test_wrong_component_version_or_source_digest_leaves_relay_missing(tmp_path):
    """Catches accepting a descriptor that names the wrong reviewed source."""
    from harness.bundled_lane_admission import admit_bundled_lane

    wrong_version = _descriptor(version="9.9.9", source_digest="sha256:" + canonical_sha256(
        _descriptor()["source"]["files"]))
    result = admit_bundled_lane(
        "relay", executable="gateway.exe", environ={},
        descriptor_path=_write_descriptor(tmp_path, wrong_version),
        importable_fn=lambda _name: True,
        expected={**_expected(wrong_version), "version": "0.2.0"},
    )
    assert result.launch is None
    assert "bundled_component_version_mismatch" in result.blocking_codes

    descriptor = _descriptor(source_digest="sha256:" + "9" * 64)
    result = admit_bundled_lane(
        "relay", executable="gateway.exe", environ={},
        descriptor_path=_write_descriptor(tmp_path, descriptor),
        importable_fn=lambda _name: True,
        expected={**_expected(descriptor),
                  "source_manifest_sha256": SOURCE_DIGEST},
    )
    assert result.launch is None
    assert "bundled_source_digest_mismatch" in result.blocking_codes


def test_missing_relay_local_mcp_module_leaves_relay_missing(tmp_path):
    """Catches admitting source metadata when the bundled module is absent."""
    from harness.bundled_lane_admission import admit_bundled_lane

    descriptor = _descriptor(source_digest="sha256:" + canonical_sha256(
        _descriptor()["source"]["files"]))
    result = admit_bundled_lane(
        "relay", executable="gateway.exe", environ={},
        descriptor_path=_write_descriptor(tmp_path, descriptor),
        importable_fn=lambda _name: False,
        expected=_expected(descriptor),
    )

    assert result.launch is None
    assert "bundled_module_missing" in result.blocking_codes


def test_frozen_relay_auto_uses_gateway_self_child_and_not_path(monkeypatch):
    """Catches frozen Relay selecting a package, runtime_python, or PATH executable."""
    from harness import bundled_lane_admission, lanes
    from harness.mcp_client import LaunchSpec

    admission = bundled_lane_admission.BundledLaneAdmission(
        launch=LaunchSpec(("D:/app/flywheel-gateway.exe",
                           "--bundled-lane-mcp", "relay"),
                          inherit_env=False, hide_window=True,
                          allowed_tools=("relay.status",)),
        component={"descriptor_sha256": DESCRIPTOR_DIGEST,
                   "source_commit": RELAY_COMMIT,
                   "source_manifest_sha256": SOURCE_DIGEST,
                   "allowed_tools": ["relay.status"]},
        blocking_codes=(),
    )
    calls = []
    monkeypatch.setattr(lanes, "read_registry", lambda: {})
    monkeypatch.setattr(lanes, "resolve_source_repo", lambda _lane: None)
    monkeypatch.setattr(lanes, "_frozen", lambda: True)
    monkeypatch.setattr(lanes.sys, "executable", "D:/app/flywheel-gateway.exe")
    monkeypatch.setattr(bundled_lane_admission, "admit_bundled_lane",
                        lambda *args, **kwargs: calls.append(args) or admission)

    runtime = lanes.resolve_lane_runtime("relay")

    assert calls
    assert runtime.present is True
    assert runtime.selected_runtime == "bundled"
    assert runtime.launch == admission.launch
    assert runtime.launch.allowed_tools == ("relay.status",)
    assert lanes.resolve_mcp_command("relay") == []
    assert runtime.to_dict()["bundled_component"]["descriptor_sha256"] == DESCRIPTOR_DIGEST


def test_frozen_relay_package_profile_still_refuses_ambiguous_distribution(monkeypatch, tmp_path):
    """Catches accidental removal of Relay's PyPI collision guard."""
    from harness import lanes

    metadata_calls = []
    monkeypatch.setattr(lanes, "read_registry", lambda: {
        "relay": {"runtime_profile": "package",
                  "runtime_python": str(tmp_path / "python.exe")}
    })
    monkeypatch.setattr(lanes, "resolve_source_repo", lambda _lane: None)
    monkeypatch.setattr(lanes, "_frozen", lambda: True)
    monkeypatch.setattr(lanes, "_installed_version",
                        lambda *args: metadata_calls.append(args) or "0.2.0")
    monkeypatch.setattr(lanes, "_package_runtime_version",
                        lambda *args: metadata_calls.append(args) or "0.2.0")

    runtime = lanes.resolve_lane_runtime("relay")

    assert metadata_calls == []
    assert runtime.launch is None
    assert runtime.blocking_codes == ("package_distribution_disabled",)
