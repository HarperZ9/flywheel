"""Lane MCP servers start with a minimal environment, never the parent's.

Every pip and npm lane is separately packaged code. Before this boundary each one
inherited the gateway's whole environment, so a provider key exported for one
purpose reached every lane process. These tests pin the contract: a fake provider
key set in the parent is absent in the launched lane, PATH and a manifest-declared
variable arrive, and an extra variable arrives only when the operator grants it
by name in the lane registry.
"""
from __future__ import annotations

import dataclasses
import json
import re
import sys

import pytest

import harness.lanes as ln
from harness.mcp_client import StdioTransport

FAKE_KEYS = {
    "OPENROUTER_API_KEY": "sk-test-not-a-real-key",
    "ANTHROPIC_API_KEY": "sk-test-not-a-real-key",
    "OPENAI_API_KEY": "sk-test-not-a-real-key",
}
_PROBE = (
    "import json, os, sys; "
    "names = ('OPENROUTER_API_KEY', 'ANTHROPIC_API_KEY', 'OPENAI_API_KEY', "
    "'PATH', 'FAKE_LANE_SETTING', 'FAKE_OPERATOR_GRANT', 'FAKE_UNDECLARED'); "
    "sys.stdout.write(json.dumps({n: n in os.environ for n in names}) + chr(10)); "
    "sys.stdout.flush()"
)


def _parent_env(monkeypatch):
    for name, value in FAKE_KEYS.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("FAKE_LANE_SETTING", "declared-value")
    monkeypatch.setenv("FAKE_OPERATOR_GRANT", "granted-value")
    monkeypatch.setenv("FAKE_UNDECLARED", "undeclared-value")


def _registry(monkeypatch, tmp_path, rows):
    path = tmp_path / "lanes.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    monkeypatch.setattr(ln, "LANE_REGISTRY_PATH", path)


def _probe_lane(monkeypatch, tmp_path, *, rows=None, declared=()):
    # Built without the env_vars keyword so the leak assertions, not a
    # TypeError, are what fail on code that predates the field.
    lane = ln.Lane("probe", "probe-dist", sys.executable, ("-c", _PROBE), "pip",
                   "0.1.0", "env probe", "test")
    if declared:
        assert hasattr(lane, "env_vars"), "Lane has no env_vars declaration field"
        lane = dataclasses.replace(lane, env_vars=tuple(declared))
    monkeypatch.setattr(ln, "LANES", {"probe": lane})
    monkeypatch.setattr(ln, "resolve_source_repo", lambda lane: None)
    monkeypatch.setattr(ln, "_importable", lambda top: False)
    monkeypatch.setattr(ln, "_installed_version", lambda lane: "0.1.0")
    _registry(monkeypatch, tmp_path, rows or {})
    return ln.resolve_mcp_launch("probe")


def _child_view(launch) -> dict:
    transport = StdioTransport(launch, timeout=20.0)
    try:
        return transport.receive()
    finally:
        transport.close()


def test_launched_pip_lane_does_not_see_parent_provider_keys(tmp_path, monkeypatch):
    _parent_env(monkeypatch)
    launch = _probe_lane(monkeypatch, tmp_path)
    seen = _child_view(launch)
    assert seen["OPENROUTER_API_KEY"] is False
    assert seen["ANTHROPIC_API_KEY"] is False
    assert seen["OPENAI_API_KEY"] is False
    assert seen["FAKE_UNDECLARED"] is False
    assert seen["PATH"] is True


def test_manifest_declared_variable_reaches_the_lane(tmp_path, monkeypatch):
    _parent_env(monkeypatch)
    launch = _probe_lane(monkeypatch, tmp_path, declared=("FAKE_LANE_SETTING",))
    seen = _child_view(launch)
    assert seen["FAKE_LANE_SETTING"] is True
    assert seen["OPENROUTER_API_KEY"] is False


def test_operator_grant_admits_one_named_variable(tmp_path, monkeypatch):
    _parent_env(monkeypatch)
    launch = _probe_lane(monkeypatch, tmp_path, rows={
        "probe": {"env_allow": ["FAKE_OPERATOR_GRANT"]}})
    seen = _child_view(launch)
    assert seen["FAKE_OPERATOR_GRANT"] is True
    assert seen["OPENROUTER_API_KEY"] is False
    assert seen["FAKE_UNDECLARED"] is False


def test_invalid_operator_grant_is_named_and_dropped(tmp_path, monkeypatch):
    _parent_env(monkeypatch)
    _probe_lane(monkeypatch, tmp_path, rows={
        "probe": {"env_allow": ["FAKE_OPERATOR_GRANT", "*", "PATH=x", 7]}})
    from harness import lane_env
    row = {"env_allow": ["FAKE_OPERATOR_GRANT", "*", "PATH=x", 7]}
    assert lane_env.operator_grants(row) == (("FAKE_OPERATOR_GRANT",), ("env_allow_invalid",))
    runtime = ln.resolve_lane_runtime("probe")
    assert "FAKE_OPERATOR_GRANT" in dict(runtime.launch.env_overrides)
    assert "env_allow_invalid" in runtime.mismatch_codes
    assert runtime.blocking_codes == ()


def test_env_allow_that_is_not_a_list_is_named_and_ignored(tmp_path, monkeypatch):
    _parent_env(monkeypatch)
    _probe_lane(monkeypatch, tmp_path, rows={"probe": {"env_allow": "OPENAI_API_KEY"}})
    runtime = ln.resolve_lane_runtime("probe")
    assert "OPENAI_API_KEY" not in dict(runtime.launch.env_overrides)
    assert "env_allow_invalid" in runtime.mismatch_codes


@pytest.mark.parametrize("name", sorted(
    name for name, lane in ln.LANES.items() if lane.kind in {"pip", "npm"}))
def test_every_pip_and_npm_lane_launch_is_scrubbed(name, tmp_path, monkeypatch):
    _parent_env(monkeypatch)
    monkeypatch.setattr(ln, "_frozen", lambda: False)
    monkeypatch.setattr(ln, "_installed_version", lambda lane: lane.version)
    _registry(monkeypatch, tmp_path, {})
    try:
        launch = ln.resolve_mcp_launch(name)
    except ln.LaneRuntimeError:
        pytest.skip(f"{name} has no launchable runtime on this host")
    env = dict(launch.env_overrides)
    assert launch.inherit_env is False
    for key in FAKE_KEYS:
        assert key not in env
    assert "FAKE_UNDECLARED" not in env
    assert "PATH" in {key.upper() for key in env}


def test_frozen_non_payload_npm_lane_is_scrubbed(tmp_path, monkeypatch):
    _parent_env(monkeypatch)
    monkeypatch.setattr(ln, "_frozen", lambda: True)
    _registry(monkeypatch, tmp_path, {})
    launch = ln.resolve_mcp_launch("learn")
    assert launch.argv == ("node", "src/mcp.mjs")
    assert launch.inherit_env is False
    assert not set(FAKE_KEYS) & set(dict(launch.env_overrides))


def test_source_launch_keeps_pythonpath_and_drops_keys(tmp_path, monkeypatch):
    _parent_env(monkeypatch)
    source = tmp_path / "public" / "index"
    (source / "src" / "index_graph").mkdir(parents=True)
    (source / "src" / "index_graph" / "__init__.py").write_text(
        "__version__ = %r\n" % ln.LANES["index"].version, "utf-8")
    monkeypatch.setattr(ln, "resolve_source_repo",
                        lambda lane: source if lane.name == "index" else None)
    monkeypatch.setattr(ln, "_frozen", lambda: False)
    _registry(monkeypatch, tmp_path, {})
    launch = ln.resolve_mcp_launch("index")
    env = dict(launch.env_overrides)
    assert launch.inherit_env is False
    assert env["PYTHONSAFEPATH"] == "1"
    assert env["PYTHONPATH"].startswith(str((source / "src").resolve()))
    assert not set(FAKE_KEYS) & set(env)


# Name segments and whole names that mark a credential. Independent of the
# gateway's own secret-name check, which misses names such as
# AWS_SECRET_ACCESS_KEY and OTEL_EXPORTER_OTLP_HEADERS.
_CREDENTIAL_SEGMENTS = frozenset((
    "KEY", "KEYS", "TOKEN", "TOKENS", "SECRET", "SECRETS", "PASSWORD", "PASSWD",
    "PASS", "CREDENTIAL", "CREDENTIALS", "AUTH", "HEADERS", "DSN", "COOKIE"))
_CREDENTIAL_NAMES = frozenset(("DATABASE_URL",))


def _looks_like_credential(name: str) -> bool:
    segments = set(re.split(r"[_\W]+", name.upper()))
    return bool(segments & _CREDENTIAL_SEGMENTS) or name.upper() in _CREDENTIAL_NAMES


@pytest.mark.parametrize("name", (
    "AWS_SECRET_ACCESS_KEY", "ANTHROPIC_API_KEY", "OTEL_EXPORTER_OTLP_HEADERS",
    "FOO_KEY", "GOOGLE_APPLICATION_CREDENTIALS", "SENTRY_DSN", "DB_PASS",
    "BASIC_AUTH", "DATABASE_URL", "GITHUB_TOKEN"))
def test_credential_check_flags_known_credential_names(name):
    assert _looks_like_credential(name)


def test_manifest_declarations_never_name_a_credential():
    from harness.gateway_secret_validation import _secret_name
    for lane in ln.LANES.values():
        for name in lane.env_vars:
            assert not _secret_name(name), (lane.name, name)
            assert not _looks_like_credential(name), (lane.name, name)
