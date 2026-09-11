import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from harness import codex_app_server_auth as auth
from harness import codex_app_server_sessions as sessions
from harness.endpoints import CliBackend
from harness.local_agent import BackendError


class _FakePipe:
    def __init__(self, lines=None):
        self.lines = list(lines or [])
        self.writes = []

    def readline(self):
        return self.lines.pop(0) if self.lines else ""

    def write(self, value):
        self.writes.append(value)

    def flush(self):
        pass


class _FakeProcess:
    def __init__(self, lines):
        self.stdin = _FakePipe()
        self.stdout = _FakePipe(lines)
        self.stderr = _FakePipe()
        self.killed = False
        self.wait_count = 0

    def poll(self):
        return None

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        self.wait_count += 1
        return 0


def _json_line(obj):
    return json.dumps(obj) + "\n"


def _resolution(tmp_path, *, identity="same"):
    exe = tmp_path / "node.exe"
    exe.write_text("node", encoding="utf-8")
    script = tmp_path / "codex.js"
    script.write_text("codex", encoding="utf-8")
    return {
        "ok": True,
        "state": "available",
        "cli_present": True,
        "argv_prefix": [str(exe), str(script)],
        "executable": "node.exe",
        "identity": identity,
        "version": "codex-cli 0.153.4",
        "env": {},
        "cwd": str(tmp_path),
        "env_fingerprint": "env",
        "codex_home": "",
    }


def test_begin_login_initializes_jsonl_and_uses_only_stable_chatgpt_fields(tmp_path):
    proc = _FakeProcess([
        _json_line({"id": 1, "result": {
            "userAgent": "codex-cli 0.153.4",
            "codexHome": str(tmp_path / "codex-home")}}),
        _json_line({"id": 2, "result": {
            "type": "chatgpt",
            "authUrl": "https://auth.openai.com/oauth/authorize?state=secret",
            "loginId": "login-123",
        }}),
    ])
    created = {}

    def popen(argv, **kwargs):
        created["argv"] = argv
        created["env"] = kwargs.get("env", {})
        return proc

    out = auth.begin_login(
        resolver=lambda **_: _resolution(tmp_path),
        popen=popen,
        base_env={"OPENAI_API_KEY": "sk-secret", "CODEX_HOME": str(tmp_path / "codex-home")},
    )

    assert out["ok"] is True
    assert out["mode"] == "browser"
    assert out["authorize_url"].startswith("https://auth.openai.com/")
    sent = [json.loads(line) for line in proc.stdin.writes]
    assert sent[0]["method"] == "initialize"
    assert sent[1] == {"method": "initialized", "params": {}}
    assert sent[2]["method"] == "account/login/start"
    assert sent[2]["params"] == {"type": "chatgpt"}
    assert "chatgptAuthTokens" not in json.dumps(sent)
    assert "OPENAI_API_KEY" not in created["env"]
    assert "sk-secret" not in json.dumps(out)
    assert proc.killed is False
    sessions.close_provider("openai")
    assert proc.killed is True

def test_device_code_login_returns_only_user_display_fields(tmp_path):
    proc = _FakeProcess([
        _json_line({"id": 1, "result": {"codexHome": str(tmp_path / "codex-home")}}),
        _json_line({"id": 2, "result": {
            "type": "chatgptDeviceCode",
            "verificationUrl": "https://chatgpt.com/activate",
            "userCode": "ABCD-EFGH",
            "loginId": "login-123",
        }}),
    ])

    out = auth.begin_login(
        mode="device_code",
        resolver=lambda **_: _resolution(tmp_path),
        popen=lambda argv, **kwargs: proc,
    )

    sent = [json.loads(line) for line in proc.stdin.writes]
    assert sent[2]["params"] == {"type": "chatgptDeviceCode"}
    assert out["ok"] is True
    assert out["mode"] == "device-code"
    assert out["verification_url"] == "https://chatgpt.com/activate"
    assert out["user_code"] == "ABCD-EFGH"
    assert "login-123" not in json.dumps(out)
    sessions.close_provider("openai")

def test_untrusted_login_url_is_refused_without_echoing_the_url(tmp_path):
    proc = _FakeProcess([
        _json_line({"id": 1, "result": {}}),
        _json_line({"id": 2, "result": {
            "type": "chatgpt",
            "authUrl": "http://evil.example/?token=secret",
            "loginId": "login-123",
        }}),
    ])

    out = auth.begin_login(
        resolver=lambda **_: _resolution(tmp_path),
        popen=lambda argv, **kwargs: proc,
    )

    assert out["ok"] is False
    assert "untrusted" in out["error"]
    assert "evil.example" not in json.dumps(out)
    assert "secret" not in json.dumps(out)
    assert proc.killed is True


def test_public_status_sanitizes_account_email_and_internal_modes(tmp_path):
    proc = _FakeProcess([
        _json_line({"id": 1, "result": {}}),
        _json_line({"method": "account/updated",
                    "params": {"authMode": "chatgptAuthTokens", "planType": "pro"}}),
        _json_line({"id": 2, "result": {
            "requiresOpenaiAuth": False,
            "account": {"type": "chatgpt", "email": "person@example.com",
                        "planType": "pro"},
        }}),
    ])

    out = auth.public_status(
        resolver=lambda **_: _resolution(tmp_path, identity="sanitize"),
        popen=lambda argv, **kwargs: proc,
    )

    assert out["authenticated"] is True
    assert out["account_state"] == "authenticated"
    assert out["plan_type"] == "pro"
    assert out["email_present"] is True
    assert out["auth_mode"] == "chatgpt"
    assert out["route_ready"] is False
    assert out["run_ready"] is False
    assert out["supervised_run_ready"] is False
    assert out["readiness_check_available"] is True
    assert "person@example.com" not in json.dumps(out)
    assert "chatgptAuthTokens" not in json.dumps(out)
    assert "argv_prefix" not in out
    assert "identity" not in out
    assert str(tmp_path) not in json.dumps(out)


def test_public_status_can_run_bounded_execution_readiness_probe(tmp_path):
    proc = _FakeProcess([
        _json_line({"id": 1, "result": {"codexHome": str(tmp_path / "codex-home")}}),
        _json_line({"id": 2, "result": {
            "requiresOpenaiAuth": False,
            "account": {"type": "chatgpt", "planType": "plus"},
        }}),
    ])
    calls = []

    env = {"CODEX_HOME": str(tmp_path / "codex-home"),
           "OPENAI_API_KEY": "sk-secret", "PATH": ""}

    def resolver(**_):
        return {**_resolution(tmp_path, identity="readiness-ok"),
                "env": {"CODEX_HOME": env["CODEX_HOME"], "PATH": ""},
                "cwd": str(tmp_path), "env_fingerprint": "ready-env",
                "codex_home": env["CODEX_HOME"]}

    def runner(argv, timeout, *, env=None, cwd=None):
        calls.append((argv, timeout, env, cwd))
        return SimpleNamespace(returncode=0, stdout="usage", stderr="")

    out = auth.public_status(
        resolver=resolver,
        popen=lambda argv, **kwargs: proc,
        base_env=env,
        cwd=tmp_path,
        check_execution=True,
        readiness_runner=runner,
    )

    assert out["authenticated"] is True
    assert out["route_ready"] is True
    assert out["route_ready_reason"] == "codex_exec_help_ok"
    assert out["run_ready"] is True
    assert out["run_ready_reason"] == "codex_exec_help_ok"
    assert out["readiness_checked"] is True
    assert out["readiness_probe"] == "codex_exec_help"
    assert out["supervised_run_ready"] is False
    assert calls and calls[0][0][-2:] == ["exec", "--help"]
    assert calls[0][2]["CODEX_HOME"] == str(tmp_path / "codex-home")
    assert "OPENAI_API_KEY" not in calls[0][2]
    assert calls[0][3] == str(tmp_path)
    assert "argv_prefix" not in out
    assert "identity" not in out
    assert str(tmp_path) not in json.dumps(out)


def test_npm_powershell_wrapper_resolves_to_node_and_script(tmp_path):
    basedir = tmp_path / "npm"
    script = basedir / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
    script.parent.mkdir(parents=True)
    script.write_text("codex", encoding="utf-8")
    wrapper = basedir / "codex.ps1"
    wrapper.write_text("wrapper", encoding="utf-8")
    node = tmp_path / "node.exe"
    node.write_text("node", encoding="utf-8")

    def which(name):
        return {"codex": str(wrapper), "node.exe": str(node)}.get(name)

    result = auth.resolve_codex_cli(
        which=which,
        is_windows=True,
        version_runner=lambda argv, timeout: SimpleNamespace(
            returncode=0, stdout="codex-cli 0.153.4\n", stderr=""),
    )

    assert result["ok"] is True
    assert result["argv_prefix"] == [str(node), str(script)]
    assert result["version"] == "codex-cli 0.153.4"
    assert result["executable"] == "node.exe"


def test_bind_authenticated_backend_rechecks_identity_before_prompt(tmp_path):
    checks = iter([
        {"ok": True, **_resolution(tmp_path, identity="first"),
         "authenticated": True, "run_ready": True},
        {"ok": False, "state": "executable_changed",
         "error": "Codex executable changed before prompt execution"},
    ])
    backend = CliBackend(
        "codex-plan",
        ["codex.cmd", "exec", "--model", "{model}", "{prompt}"],
        "gpt-6-astra",
    )
    wrapped = auth.bind_authenticated_backend(
        backend,
        authenticated=lambda **_: next(checks),
        verifier=lambda identity, **_: next(checks),
    )
    commands = []
    wrapped.runner = lambda cmd: commands.append(cmd) or (0, "ok", "")

    with pytest.raises(BackendError, match="executable changed"):
        wrapped.chat([{"role": "user", "content": "hi"}],
                     system="", max_tokens=8, temperature=0, seed=0)
    assert commands == []
