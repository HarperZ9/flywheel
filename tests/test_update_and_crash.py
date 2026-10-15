"""Falsifiers for `flywheel update` and local crash reports."""
import io
import json

from harness import cli_entry, crash_report, update_cli


def test_version_order():
    pv = update_cli.parse_version
    assert pv("1.10.0") > pv("1.9.9") > pv("1.9.9rc1")
    assert pv("garbage") == ()


def test_check_names_the_upgrade_step_only_when_newer():
    newer = update_cli.check("1.5.1", "1.6.0", "pip")
    assert newer["update_available"] and "pip install --upgrade flywheel-verify" in newer["upgrade"]
    same = update_cli.check("1.6.0", "1.6.0", "app")
    assert not same["update_available"] and same["upgrade"] == ""
    assert "releases/latest" in update_cli.upgrade_step("app")


def test_latest_reads_pypi_json_and_only_that_url():
    seen = []

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def opener(req, timeout):
        seen.append(req.full_url)
        return Resp(json.dumps({"info": {"version": "9.9.9"}}).encode())
    assert update_cli.latest_from_pypi(opener=opener) == "9.9.9"
    assert seen == ["https://pypi.org/pypi/flywheel-verify/json"]


def test_offline_update_is_a_message_not_a_crash(monkeypatch, capsys):
    def boom(*a, **k):
        raise OSError("offline")
    monkeypatch.setattr(update_cli, "latest_from_pypi", boom)
    assert update_cli.main([]) == 1
    assert "could not reach PyPI" in capsys.readouterr().err


SECRET = "sk-crash-test-0123456789abcdef"


def test_crash_report_redacts_secrets_and_home(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MY_API_KEY", SECRET)
    monkeypatch.delenv("FLYWHEEL_DEBUG", raising=False)

    def explode(raw):
        raise RuntimeError(f"failed with {SECRET} in a path")
    monkeypatch.setattr(cli_entry, "main", explode)
    monkeypatch.setattr("sys.argv", ["flywheel", "doctor"])
    code = cli_entry.console_main()
    assert code == 70
    err = capsys.readouterr().err
    assert "Nothing was sent" in err
    reports = list((tmp_path / "home" / "crashes").glob("*.json"))
    assert len(reports) == 1
    text = reports[0].read_text(encoding="utf-8")
    assert SECRET not in text and "<MY_API_KEY>" in text
    data = json.loads(text)
    assert data["command"] == "doctor" and data["schema"] == "flywheel.crash-report/v1"


def test_debug_variable_re_raises(monkeypatch):
    monkeypatch.setenv("FLYWHEEL_DEBUG", "1")
    monkeypatch.setattr(cli_entry, "main", lambda raw: 1 / 0)
    try:
        cli_entry.console_main()
    except ZeroDivisionError:
        return
    raise AssertionError("FLYWHEEL_DEBUG should let the exception through")


def test_system_exit_is_not_a_crash(monkeypatch, tmp_path):
    monkeypatch.setenv("FLYWHEEL_HOME", str(tmp_path / "home"))

    def leave(raw):
        raise SystemExit(3)
    monkeypatch.setattr(cli_entry, "main", leave)
    try:
        cli_entry.console_main()
    except SystemExit as e:
        assert e.code == 3
    assert not (tmp_path / "home" / "crashes").exists()


def test_redact_leaves_short_values_alone():
    assert crash_report.redact("a b", {"X_TOKEN": "a"}) == "a b"


def test_the_installed_command_is_the_crash_reporting_entry():
    import tomllib
    from pathlib import Path
    data = tomllib.loads((Path(__file__).resolve().parent.parent / "pyproject.toml")
                         .read_text(encoding="utf-8"))
    assert data["project"]["scripts"]["flywheel"] == "harness.cli_entry:console_main"
