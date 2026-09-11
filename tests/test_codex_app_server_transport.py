import json
import os
from types import SimpleNamespace

import pytest

from harness import codex_app_server_transport as transport


class _Pipe:
    def __init__(self, lines=None):
        self.lines = list(lines or [])
        self.writes = []

    def readline(self):
        return self.lines.pop(0) if self.lines else ""

    def write(self, value):
        self.writes.append(value)

    def flush(self):
        pass


class _Proc:
    def __init__(self, lines):
        self.stdin = _Pipe()
        self.stdout = _Pipe(lines)
        self.killed = False
        self.wait_count = 0

    def poll(self):
        return None

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        self.wait_count += 1
        return 0


def _line(obj):
    return json.dumps(obj) + "\n"


@pytest.mark.parametrize("lines,exc", [
    ([_line({"id": 1, "error": {"message": "boom"}})], RuntimeError),
    ([], TimeoutError),
])
def test_handshake_failure_kills_process(lines, exc):
    proc = _Proc(lines)
    client = transport.JsonlAppServerClient(
        ["codex"], popen=lambda argv, **kwargs: proc, env={})

    with pytest.raises(exc):
        client.__enter__()

    assert proc.killed is True
    assert proc.wait_count == 1


def test_handshake_byte_limit_kills_process(monkeypatch):
    monkeypatch.setattr(transport, "MAX_RESPONSE_BYTES", 20)
    proc = _Proc([_line({"id": 1, "result": {"padding": "x" * 40}})])
    client = transport.JsonlAppServerClient(
        ["codex"], popen=lambda argv, **kwargs: proc, env={})

    with pytest.raises(TimeoutError):
        client.__enter__()

    assert proc.killed is True
    assert proc.wait_count == 1


def test_executable_identity_changes_for_same_size_same_mtime_swap(tmp_path):
    exe = tmp_path / "node.exe"
    script = tmp_path / "codex.js"
    exe.write_text("node", encoding="utf-8")
    script.write_text("aaaa", encoding="utf-8")
    first = transport.identity([str(exe), str(script)])
    stat = script.stat()
    script.write_text("bbbb", encoding="utf-8")
    os.utime(script, ns=(stat.st_atime_ns, stat.st_mtime_ns))

    assert transport.identity([str(exe), str(script)]) != first


def test_version_probe_uses_sanitized_env_and_cwd(tmp_path):
    script = tmp_path / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
    script.parent.mkdir(parents=True)
    script.write_text("codex", encoding="utf-8")
    node = tmp_path / "node.exe"
    node.write_text("node", encoding="utf-8")
    wrapper = tmp_path / "codex.ps1"
    wrapper.write_text("wrapper", encoding="utf-8")
    seen = {}

    def runner(argv, timeout, *, env=None, cwd=None):
        seen.update({"argv": argv, "env": env, "cwd": cwd})
        return SimpleNamespace(returncode=0, stdout="codex-cli 0.153.4\n")

    result = transport.resolve_codex_cli(
        which=lambda name: {"codex": str(wrapper), "node.exe": str(node)}.get(name),
        is_windows=True,
        env={"PATH": "", "CODEX_HOME": str(tmp_path / "home"),
             "OPENAI_API_KEY": "sk-secret"},
        cwd=tmp_path,
        version_runner=runner,
    )

    assert result["ok"] is True
    assert seen["env"]["CODEX_HOME"] == str(tmp_path / "home")
    assert "OPENAI_API_KEY" not in seen["env"]
    assert seen["cwd"] == str(tmp_path)
