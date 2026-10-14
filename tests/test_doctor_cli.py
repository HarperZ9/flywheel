"""Falsifiers for `flywheel doctor`: read-only, never prints a key, FAILs only on a real blocker."""
import json

from harness import doctor_cli


SECRET = "sk-test-DOCTOR-must-never-print-0123456789"


def test_keys_are_reported_by_name_never_value():
    c = doctor_cli.check_keys({"ANTHROPIC_API_KEY": SECRET, "OPENAI_API_KEY": "  "})
    assert c["status"] == "OK"
    assert "ANTHROPIC_API_KEY" in c["detail"]
    assert "OPENAI_API_KEY" not in c["detail"]          # blank is not set
    assert SECRET not in json.dumps(c)


def test_no_keys_is_a_warning_with_a_next_step():
    c = doctor_cli.check_keys({})
    assert c["status"] == "WARN" and c["fix"]


def test_full_report_never_contains_a_key_value(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("OPENAI_API_KEY", SECRET)
    monkeypatch.setattr(doctor_cli, "check_local_servers", lambda: doctor_cli._check(
        "local models", "WARN", "stubbed"))
    for flag in ([], ["--json"]):
        doctor_cli.main(flag)
        out = capsys.readouterr().out
        assert SECRET not in out
        assert "OPENAI_API_KEY" in out


def test_json_report_has_schema_and_every_check(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(doctor_cli, "check_local_servers", lambda: doctor_cli._check(
        "local models", "WARN", "stubbed"))
    code = doctor_cli.main(["--json"])
    report = json.loads(capsys.readouterr().out)
    assert report["schema"] == "flywheel.doctor/v1"
    names = [c["check"] for c in report["checks"]]
    assert names == ["python", "flywheel", "home", "git", "provider keys",
                     "local models", "relay"]
    assert code == 0                                      # warnings do not fail


def test_unwritable_home_fails(tmp_path):
    blocker = tmp_path / "file-not-dir"
    blocker.write_text("x", encoding="utf-8")
    c = doctor_cli.check_home({"FLYWHEEL_HOME": str(blocker / "home")})
    assert c["status"] == "FAIL" and "FLYWHEEL_HOME" in c["fix"]


def test_missing_git_is_a_warning_not_a_failure():
    c = doctor_cli.check_git(which=lambda name: None)
    assert c["status"] == "WARN"


def test_local_server_probe_is_loopback_only():
    seen = []
    doctor_cli.check_local_servers(probe=lambda url, t: seen.append(url) or False)
    assert seen and all(u.startswith("http://127.0.0.1:") for u in seen)


def test_doctor_is_a_packaged_command():
    from harness import cli_entry
    assert cli_entry._PACKAGED["doctor"] == "harness.doctor_cli"
