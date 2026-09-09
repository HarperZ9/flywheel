"""Public lane runtime status never echoes malformed local runtime metadata."""
from __future__ import annotations

import json

import pytest

import harness.lanes as lanes
from harness.lane_runtime_versions import normalize_public_version
from harness.lanes_registry import Lane


def _registry(monkeypatch, tmp_path, name, row):
    path = tmp_path / "lanes.json"
    path.write_text(json.dumps({name: row}), encoding="utf-8")
    monkeypatch.setattr(lanes, "LANE_REGISTRY_PATH", path)


def _fake_python(tmp_path, name="python.exe"):
    path = tmp_path / ".ssh" / name
    path.parent.mkdir()
    path.write_text("", encoding="utf-8")
    return path


def _index_source(tmp_path, version):
    package = tmp_path / "public" / "index" / "src" / "index_graph"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(
        f'__version__ = "{version}"\n', encoding="utf-8")
    return tmp_path / "public" / "index"


@pytest.mark.parametrize("version", [
    "2.12.0",
    "2.12.0rc1",
    "2.12.0.dev1+local.1",
    "2.12.0-beta.1+build.7",
])
def test_version_validator_accepts_package_versions(version):
    assert normalize_public_version(version) == version


@pytest.mark.parametrize("bad", [
    123,
    {},
    "C:/Users/Operator/.ssh/private-runtime-version-token",
    "2.12.0\nprivate-runtime-version-token",
    "1.0.0 ",
    "9" * 129,
])
def test_invalid_runtime_version_is_null_and_never_echoed(tmp_path, monkeypatch, bad):
    python = _fake_python(tmp_path)
    _registry(monkeypatch, tmp_path, "index", {
        "runtime_profile": "package",
        "runtime_version": bad,
        "runtime_python": str(python),
    })
    monkeypatch.setattr(lanes, "resolve_source_repo", lambda lane: None)
    monkeypatch.setattr(
        lanes, "_package_runtime_version", lambda lane, runtime: "2.12.0",
        raising=False)
    status = lanes.lane_status("index", probe=False)
    runtime = status["resolved_runtime"]

    assert status["status"] == lanes.MISSING
    assert runtime["runtime_expected_version"] is None
    assert "runtime_version_invalid" in runtime["mismatch_codes"]
    encoded = json.dumps(status)
    assert "private-runtime-version-token" not in encoded
    assert str(bad) not in encoded


def test_invalid_observed_package_version_is_null_and_named(tmp_path, monkeypatch):
    secretish = "C:/Users/Operator/.ssh/private-installed-version-token"
    python = _fake_python(tmp_path)
    _registry(monkeypatch, tmp_path, "index", {
        "runtime_profile": "package",
        "runtime_version": "2.12.0",
        "runtime_python": str(python),
    })
    monkeypatch.setattr(lanes, "resolve_source_repo", lambda lane: None)
    monkeypatch.setattr(
        lanes, "_package_runtime_version", lambda lane, runtime: secretish,
        raising=False)
    status = lanes.lane_status("index", probe=False)

    assert status["installed_version"] is None
    assert status["resolved_runtime"]["installed_version"] is None
    assert "installed_version_invalid" in status["resolved_runtime"]["mismatch_codes"]
    assert secretish not in json.dumps(status)


def test_invalid_source_version_is_null_and_named(tmp_path, monkeypatch):
    secretish = "C:/Users/Operator/.ssh/private-source-version-token"
    source = _index_source(tmp_path, secretish)
    _registry(monkeypatch, tmp_path, "index", {"runtime_profile": "source"})
    monkeypatch.setattr(lanes, "resolve_source_repo", lambda lane: source)
    monkeypatch.setattr(lanes, "_installed_version", lambda lane: None)
    status = lanes.lane_status("index", probe=False)

    runtime = status["resolved_runtime"]
    assert runtime["source_version"] is None
    assert "source_version_invalid" in runtime["mismatch_codes"]
    assert secretish not in json.dumps(status)


def test_invalid_declared_expected_version_is_null_and_named(tmp_path, monkeypatch):
    secretish = "C:/Users/Operator/.ssh/private-expected-version-token"
    lane = Lane("bad", "bad-pkg", "bad", ("mcp",), "pip", secretish,
                "role", "organ", py_module="bad_pkg")
    monkeypatch.setitem(lanes.LANES, "bad", lane)
    _registry(monkeypatch, tmp_path, "bad", {"runtime_profile": "package"})
    monkeypatch.setattr(lanes, "resolve_source_repo", lambda lane: None)
    monkeypatch.setattr(lanes, "_installed_version", lambda lane: "2.12.0")
    status = lanes.lane_status("bad", probe=False)

    runtime = status["resolved_runtime"]
    assert status["expected_version"] is None
    assert runtime["expected_version"] is None
    assert runtime["runtime_expected_version"] is None
    assert "expected_version_invalid" in runtime["mismatch_codes"]
    assert secretish not in json.dumps(status)


def test_runtime_python_basename_is_not_public_status_metadata(tmp_path, monkeypatch):
    python = _fake_python(tmp_path, "private-python-token.exe")
    _registry(monkeypatch, tmp_path, "index", {
        "runtime_profile": "package",
        "runtime_version": "2.12.0",
        "runtime_python": str(python),
    })
    monkeypatch.setattr(lanes, "resolve_source_repo", lambda lane: None)
    monkeypatch.setattr(
        lanes, "_package_runtime_version", lambda lane, runtime: "2.12.0",
        raising=False)
    status = lanes.lane_status("index", probe=False)

    assert "private-python-token" not in json.dumps(status)
