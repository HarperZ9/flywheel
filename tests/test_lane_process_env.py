"""Every child process that runs lane code gets the lane environment.

The MCP launch of a pip or npm lane is confined by lane_env.confine_lane_launch.
The gateway also runs lane code outside that launch: the index and chorus CLIs,
index router jobs, the canon context child, the telos kernels, the gather and
crucible CLIs, and the package version probe. Each of these used to pass the
gateway's whole environment. These tests set fake provider keys in the parent
and check that each child environment drops them and keeps PATH. No test uses a
real key.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

FAKE_KEYS = {
    "OPENROUTER_API_KEY": "sk-test-not-a-real-key",
    "ANTHROPIC_API_KEY": "sk-test-not-a-real-key",
}
_PROBE = (
    "import json, os; "
    "names = ('OPENROUTER_API_KEY', 'ANTHROPIC_API_KEY', 'PATH'); "
    "seen = {n: n in os.environ for n in names}; "
    "print(json.dumps({'seen': seen, 'corpora': [], 'digests': []}))"
)


@pytest.fixture
def parent_keys(tmp_path, monkeypatch):
    import harness.lanes as ln
    for name, value in FAKE_KEYS.items():
        monkeypatch.setenv(name, value)
    registry = tmp_path / "lanes.json"
    registry.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(ln, "LANE_REGISTRY_PATH", registry)
    return registry


class _Capture:
    """Stands in for subprocess.run and keeps the env each call passed."""

    def __init__(self, stdout="{}"):
        self.envs = []
        self.stdout = stdout

    def __call__(self, cmd, *args, **kwargs):
        self.envs.append(kwargs.get("env"))
        return subprocess.CompletedProcess(cmd, 0, stdout=self.stdout, stderr="")


def _assert_scrubbed(env):
    assert env is not None, "the child inherited the whole parent environment"
    upper = {key.upper() for key in env}
    for key in FAKE_KEYS:
        assert key not in upper
    assert "PATH" in upper


def test_index_view_child_does_not_see_provider_keys(parent_keys, tmp_path, monkeypatch):
    import harness.index_bridge as ib
    monkeypatch.setattr(ib, "_index_argv", lambda: [sys.executable, "-c", _PROBE])
    out = ib.index_view(str(tmp_path), "map", timeout=30)
    seen = out["result"]["seen"]
    assert seen["OPENROUTER_API_KEY"] is False
    assert seen["ANTHROPIC_API_KEY"] is False
    assert seen["PATH"] is True


def test_chorus_digest_child_does_not_see_provider_keys(parent_keys, tmp_path, monkeypatch):
    import harness.chorus_bridge as cb
    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text("", encoding="utf-8")
    monkeypatch.setattr(cb, "_chorus_argv", lambda: [sys.executable, "-c", _PROBE])
    out = cb.discourse_digest(str(corpus))
    seen = out["result"]["seen"]
    assert seen["OPENROUTER_API_KEY"] is False
    assert seen["PATH"] is True


def test_chorus_corpora_and_digests_pass_the_lane_env(parent_keys, tmp_path, monkeypatch):
    import harness.chorus_bridge as cb
    capture = _Capture(stdout=json.dumps({"corpora": [], "digests": []}))
    monkeypatch.setattr(cb, "_chorus_argv", lambda: ["chorus"])
    monkeypatch.setattr(cb.subprocess, "run", capture)
    cb.list_corpora(str(tmp_path))
    cb.recent_digests(str(tmp_path))
    assert len(capture.envs) == 2
    for env in capture.envs:
        _assert_scrubbed(env)


def test_index_router_job_env_keeps_only_the_job_dir_extra(parent_keys, tmp_path):
    from harness import index_jobs
    env = index_jobs._env(tmp_path)
    _assert_scrubbed(env)
    assert env["INDEX_ROUTER_JOB_DIR"] == str(tmp_path / "index-router-jobs")


def test_canon_context_child_env_drops_provider_keys(parent_keys, tmp_path, monkeypatch):
    from harness.context_memory_bridge import CanonContextMcpClient
    db = str((tmp_path / "context.db").resolve())
    monkeypatch.setenv("FLYWHEEL_CANON_CONTEXT_DB", db)
    client = CanonContextMcpClient.from_environment()
    _assert_scrubbed(client.env)
    assert client.env["CANON_CONTEXT_DB"] == db
    assert client.env["CANON_CONTEXT_SCOPE"] == "trusted-local-process"
    default = CanonContextMcpClient(command=["canon"])
    _assert_scrubbed(default.env)


def test_package_version_probe_passes_the_lane_env(parent_keys, monkeypatch):
    import harness.lane_runtime_support as support
    from harness.lanes_registry import LANES
    capture = _Capture(stdout="1.0.0\n")
    monkeypatch.setattr(support.subprocess, "run", capture)
    assert support.package_runtime_version(LANES["index"], sys.executable) == "1.0.0"
    (env,) = capture.envs
    _assert_scrubbed(env)


def test_telos_kernel_child_passes_the_lane_env(parent_keys, tmp_path, monkeypatch):
    import harness.telos_kernels as tk
    capture = _Capture(stdout=json.dumps({"ok": True}))
    module = tmp_path / "kernels.mjs"
    module.write_text("", encoding="utf-8")
    monkeypatch.setattr(tk, "_module_path", lambda: module)
    monkeypatch.setattr(tk.subprocess, "run", capture)
    kernel = sorted(tk.KERNELS)[0]
    tk.run_kernel(kernel, {})
    (env,) = capture.envs
    _assert_scrubbed(env)


@pytest.mark.parametrize("module_name", ("harness.live_feeds", "harness.science_bench"))
def test_gather_and_crucible_cli_runners_pass_the_lane_env(parent_keys, monkeypatch,
                                                          module_name):
    import importlib
    module = importlib.import_module(module_name)
    capture = _Capture(stdout="{}")
    monkeypatch.setattr(module.subprocess, "run", capture)
    lane = "gather" if module_name.endswith("live_feeds") else "crucible"
    module._shell([lane, "--version"])
    (env,) = capture.envs
    _assert_scrubbed(env)


def test_operator_grant_reaches_a_bridge_child(parent_keys, tmp_path, monkeypatch):
    import harness.index_bridge as ib
    parent_keys.write_text(json.dumps({"index": {"env_allow": ["ANTHROPIC_API_KEY"]}}),
                           encoding="utf-8")
    monkeypatch.setattr(ib, "_index_argv", lambda: [sys.executable, "-c", _PROBE])
    seen = ib.index_view(str(tmp_path), "map", timeout=30)["result"]["seen"]
    assert seen["ANTHROPIC_API_KEY"] is True
    assert seen["OPENROUTER_API_KEY"] is False


def test_unreadable_registry_grants_nothing(tmp_path, monkeypatch):
    import harness.lanes as ln
    from harness.lane_env import lane_process_environment
    monkeypatch.setattr(ln, "LANE_REGISTRY_PATH", Path(tmp_path))  # a directory
    env = lane_process_environment("index", environ={
        "PATH": "p", "ANTHROPIC_API_KEY": "sk-test-not-a-real-key"})
    assert env == {"PATH": "p"}
