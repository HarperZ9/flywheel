import json
from types import SimpleNamespace

from harness import codex_app_server_auth as auth


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

    def poll(self):
        return None

    def kill(self):
        pass

    def wait(self, timeout=None):
        return 0


def _line(obj):
    return json.dumps(obj) + "\n"


def _resolution(tmp_path):
    exe = tmp_path / "node.exe"; exe.write_text("node", encoding="utf-8")
    script = tmp_path / "codex.js"; script.write_text("codex", encoding="utf-8")
    return {"ok": True, "state": "available", "cli_present": True,
            "argv_prefix": [str(exe), str(script)], "executable": "node.exe",
            "identity": "same", "version": "codex-cli 0.153.4",
            "env": {"CODEX_HOME": str(tmp_path / "home")},
            "cwd": str(tmp_path), "env_fingerprint": "same-env",
            "codex_home": str(tmp_path / "home")}


def test_cached_route_readiness_does_not_survive_account_loss(tmp_path):
    authed = _Proc([
        _line({"id": 1, "result": {"codexHome": str(tmp_path / "home")}}),
        _line({"id": 2, "result": {
            "requiresOpenaiAuth": False,
            "account": {"type": "chatgpt", "planType": "plus"}}}),
    ])
    out = auth.public_status(
        resolver=lambda **_: _resolution(tmp_path),
        popen=lambda argv, **kwargs: authed,
        check_execution=True,
        readiness_runner=lambda *a, **k: SimpleNamespace(returncode=0),
    )
    assert out["route_ready"] is True

    unauth = _Proc([
        _line({"id": 1, "result": {"codexHome": str(tmp_path / "home")}}),
        _line({"id": 2, "result": {
            "requiresOpenaiAuth": True,
            "account": {"type": "chatgpt", "planType": "plus"}}}),
    ])
    out = auth.public_status(
        resolver=lambda **_: _resolution(tmp_path),
        popen=lambda argv, **kwargs: unauth,
    )

    assert out["authenticated"] is False
    assert out["route_ready"] is False
    assert out["run_ready"] is False
