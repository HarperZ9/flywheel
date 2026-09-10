import json
from types import SimpleNamespace

import pytest

from harness import claude_cli_auth as cca


def _exe(tmp_path, name="claude.exe", body=b"claude"):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return path


def _which(path):
    return lambda name: str(path) if name == "claude.exe" else None


def _status(tmp_path, stdout, *, code=0):
    exe = _exe(tmp_path)
    seen = []

    def runner(argv, timeout):
        seen.append(argv)
        return SimpleNamespace(
            returncode=code, stdout=stdout, stderr="stderr SECRET")

    result = cca.account_status(
        which=_which(exe), runner=runner, is_windows=True)
    return result, seen, exe


def test_resolution_prefers_native_exe_over_warden_wrapper(tmp_path):
    native = _exe(tmp_path / "native")
    wrapper = _exe(tmp_path / ".warden" / "bin", name="claude")
    result = cca.resolve_official_cli(
        which=lambda name: {"claude.exe": str(native), "claude": str(wrapper)}.get(name),
        is_windows=True,
    )

    assert result["ok"] is True
    assert result["path"] == str(native)
    assert result["executable"] == "claude.exe"


def test_resolution_rejects_warden_wrapper_without_native_exe(tmp_path):
    wrapper = _exe(tmp_path / ".warden" / "bin", name="claude")
    result = cca.resolve_official_cli(
        which=lambda name: str(wrapper) if name == "claude" else None,
        is_windows=True,
    )

    assert result["ok"] is False
    assert result["state"] == "wrapper_unsupported"


def test_status_accepts_only_typed_first_party_account_shape(tmp_path):
    payload = {
        "loggedIn": True,
        "authMethod": "claude.ai",
        "apiProvider": "firstParty",
        "email": "secret@example.invalid",
        "orgName": "SECRET_ORG",
        "orgId": "SECRET_ID",
        "projectsDirectory": "C:/private/path",
        "apiKeySource": "withheld",
    }
    status, seen, exe = _status(tmp_path, json.dumps(payload))

    assert seen == [[str(exe), "auth", "status", "--json"]]
    assert status["state"] == "authenticated"
    assert status["authenticated"] is True
    assert status["auth_method"] == "claude.ai"
    assert status["api_provider"] == "firstParty"
    safe = json.dumps(status)
    assert str(exe) not in safe
    for private in ("secret@example.invalid", "SECRET_ORG", "SECRET_ID",
                    "C:/private/path", "apiKeySource", "stderr SECRET"):
        assert private not in safe


@pytest.mark.parametrize(
    "stdout",
    [
        "not json",
        json.dumps({"loggedIn": "true", "authMethod": "claude.ai",
                    "apiProvider": "firstParty"}),
        json.dumps({"loggedIn": True, "authMethod": "setup-token",
                    "apiProvider": "firstParty"}),
        json.dumps({"loggedIn": True, "authMethod": "claude.ai",
                    "apiProvider": "directApi"}),
    ],
)
def test_status_mismatches_are_unknown_not_authenticated(tmp_path, stdout):
    status, _seen, _exe = _status(tmp_path, stdout)

    assert status["state"] == "unknown"
    assert status["authenticated"] is False


def test_status_exit_zero_logged_out_is_unknown(tmp_path):
    status, _seen, _exe = _status(tmp_path, json.dumps({"loggedIn": False}))

    assert status["state"] == "unknown"
    assert status["authenticated"] is False


def test_status_exit_one_logged_out_is_not_authenticated(tmp_path):
    status, _seen, _exe = _status(
        tmp_path, json.dumps({"loggedIn": False}), code=1)

    assert status["state"] == "not_authenticated"
    assert status["authenticated"] is False


def test_begin_login_launches_auth_login_without_public_path(tmp_path):
    exe = _exe(tmp_path)
    launched = []

    def launcher(argv):
        launched.append(argv)
        return SimpleNamespace(pid=123)

    result = cca.begin_login(
        which=_which(exe), launcher=launcher, is_windows=True)

    assert result["ok"] is True
    assert result["mode"] == "official-cli"
    assert launched == [[str(exe), "auth", "login"]]
    assert str(exe) not in json.dumps(result)
    assert result["executable"] == "claude.exe"


def test_begin_login_detects_executable_swap_before_spawn(tmp_path):
    first = _exe(tmp_path / "first", body=b"first")
    second = _exe(tmp_path / "second", body=b"second")
    paths = [str(first), str(second)]

    def which(name):
        return paths.pop(0) if name == "claude.exe" and paths else None

    def launcher(_argv):
        raise AssertionError("login should not launch after executable swap")

    result = cca.begin_login(
        which=which, launcher=launcher, is_windows=True)

    assert result["ok"] is False
    assert result["state"] == "executable_changed"
