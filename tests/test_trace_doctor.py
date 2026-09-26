"""7.1 doctor: lists hook mounts, checks the channel, and never runs or prints
anything taken from a settings file."""
import json
import sys

import pytest

from capture_channel_fixture import hook_env, run_hook, running_gateway, stop_event
from trace_redact_fakes import credential_fakes


@pytest.fixture
def planted(tmp_path):
    home, claude, codex, cwd = (tmp_path / n for n in ("home", "claude", "codex", "proj"))
    for path in (home, claude, codex, cwd / ".claude"):
        path.mkdir(parents=True)
    marker = tmp_path / "EXECUTED"
    python = sys.executable
    fake = credential_fakes()["sk_api_key"]
    good = f'"{python}" -m harness.capture_hooks stop --client claude-code'
    trap = f'"{python}" -c "open(r\'{marker}\', \'w\')" harness.capture_hooks'
    (claude / "settings.json").write_text(json.dumps({"hooks": {
        "Stop": [{"hooks": [{"type": "command", "command": good}]}],
        "SessionStart": [{"hooks": [{"type": "command", "command": trap}]}]}}))
    (cwd / ".claude" / "settings.local.json").write_text(json.dumps({
        "env": {"OPENAI_API_KEY": fake, "FLYWHEEL_CAPTURE": "off"},
        "hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command":
                  f'"{python}" -m harness.capture_hooks_gone prompt'}]}]}}))
    (codex / "hooks.json").write_text(json.dumps({"hooks": {"Stop": [{"hooks": [
        {"type": "command", "command": f'"{python}" -m harness.capture_hooks stop '
                                       f'--client codex'}]}]}}))
    environ = {"CLAUDE_CONFIG_DIR": str(claude), "CODEX_HOME": str(codex)}
    return {"home": home, "cwd": cwd, "environ": environ, "marker": marker, "fake": fake}


def _doctor(p, **kw):
    from harness.trace_doctor import run_doctor
    return run_doctor(p["home"], environ=p["environ"], cwd=p["cwd"], **kw)


def _text(checks) -> str:
    from harness.trace_doctor import render
    return "\n".join(render(checks))


def _by_name(checks):
    return {c.name: c for c in checks}


def test_planted_claude_and_codex_mounts_are_listed(planted):
    text = _text(_doctor(planted))
    assert "Stop" in text and "UserPromptSubmit" in text
    assert "codex hooks.json" in text and "claude settings.json" in text
    assert "project .claude/settings.local.json" in text


def test_a_mount_whose_module_is_missing_fails(planted):
    mounts = _by_name(_doctor(planted))["hook mounts"]
    assert mounts.state == "FAIL"
    assert "harness.capture_hooks_gone" in mounts.detail


def test_nothing_from_a_settings_file_is_executed(planted):
    _doctor(planted)
    assert not planted["marker"].exists()


def test_the_synthetic_run_uses_the_flywheel_module_not_a_settings_command(
        planted, monkeypatch):
    with running_gateway(planted["home"], monkeypatch):
        checks = _doctor(planted, synthetic=True)
    assert not planted["marker"].exists()
    assert _by_name(checks)["synthetic turn"].state == "PASS"


def test_a_planted_key_in_an_env_block_appears_nowhere(planted, monkeypatch):
    from harness.trace_doctor import to_json
    with running_gateway(planted["home"], monkeypatch):
        checks = _doctor(planted, synthetic=True)
    fake = planted["fake"]
    assert fake not in _text(checks) and fake not in json.dumps(to_json(checks))
    stored = b"".join(p.read_bytes() for p in planted["home"].rglob("*") if p.is_file())
    assert fake.encode() not in stored
    assert "FLYWHEEL_CAPTURE" in _by_name(checks)["hook mounts"].detail


def test_the_channel_check_passes_against_a_running_gateway(planted, monkeypatch):
    with running_gateway(planted["home"], monkeypatch):
        channel = _by_name(_doctor(planted))["capture channel"]
    assert channel.state == "PASS", channel.detail


def test_the_channel_check_fails_by_name_without_a_gateway(planted):
    (planted["home"] / "gateway.token").write_text("synthetic-token-value")
    channel = _by_name(_doctor(planted))["capture channel"]
    assert channel.state == "FAIL" and "GATEWAY_NOT_RUNNING" in channel.detail


def test_spooled_failures_are_shown_until_acknowledged(planted, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    run_hook(planted["home"], "stop", stop_event(), cwd=work, env=hook_env())
    failures = _by_name(_doctor(planted))["capture failures"]
    assert failures.state == "WARN" and "TOKEN_MISSING" in failures.detail
    _doctor(planted, ack=True)
    assert _by_name(_doctor(planted))["capture failures"].state == "PASS"


def test_every_check_has_a_state_and_a_remedy_line(planted):
    checks = _doctor(planted)
    assert [c.number for c in checks] == list(range(1, len(checks) + 1))
    for check in checks:
        assert check.state in ("PASS", "WARN", "FAIL", "UNKNOWN")
        assert check.remedy or check.state == "PASS"
