"""A launch that does not inherit the environment passes only what it names.

Moved from test_plugin_grants.py when the program lookup made the server a real
file: the stand-in sits in the one PATH folder the launch names.
"""
import json
import os
import subprocess

from harness.mcp_client import LaunchSpec, StdioTransport


class _EmptyStream:
    def __iter__(self):
        return iter(())


class _FakeProcess:
    stdin = None
    stdout = _EmptyStream()
    stderr = _EmptyStream()

    def poll(self):
        return None


def test_non_inheriting_launch_spec_passes_only_explicit_environment(monkeypatch, tmp_path):
    marker = "ambient-value-must-not-cross"
    monkeypatch.setenv("CLOUD_ACCESS_TOKEN", marker)
    # The server must exist to start: a stand-in in the one PATH folder given.
    safe_bin = tmp_path / "safe-bin"
    safe_bin.mkdir()
    server = safe_bin / ("bounded-mcp.exe" if os.name == "nt" else "bounded-mcp")
    server.write_bytes(b"MZ")
    server.chmod(0o755)
    monkeypatch.setenv("PATH", str(safe_bin))  # Windows searches the parent's PATH
    seen = {}
    monkeypatch.setattr(subprocess, "Popen", lambda argv, **kwargs:
                        seen.update(argv=argv, kwargs=kwargs) or _FakeProcess())

    StdioTransport(LaunchSpec(
        ("bounded-mcp",), env_overrides=(("PATH", str(safe_bin)),),
        inherit_env=False))

    assert seen["kwargs"]["env"] == {"PATH": str(safe_bin)}
    assert os.path.normcase(seen["argv"][0]) == os.path.normcase(
        os.path.join(os.path.realpath(safe_bin), server.name))
    assert marker not in json.dumps(seen)
