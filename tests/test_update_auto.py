"""Falsifiers for `flywheel update --apply` and the opt-in weekly check."""
import sys
from types import SimpleNamespace

from harness import update_auto, update_cli


def test_apply_runs_this_interpreters_pip_for_the_exact_version():
    seen = []
    ok, msg = update_auto.apply("9.9.9", "pip", run=lambda argv, **k: seen.append(argv) or
                                SimpleNamespace(returncode=0, stdout="", stderr=""))
    assert ok and seen[0][:3] == [sys.executable, "-m", "pip"]
    assert seen[0][-1] == "flywheel-verify==9.9.9"


def test_apply_never_touches_the_app_or_a_checkout():
    for kind in ("app", "source"):
        ok, msg = update_auto.apply("9.9.9", kind, run=lambda *a, **k: 1 / 0)
        assert not ok and "by hand" in msg


def test_weekly_check_is_off_until_turned_on(tmp_path):
    home = str(tmp_path)
    calls = []
    assert update_auto.notice(home, "1.0.0", lambda: calls.append(1) or "2.0.0") is None
    assert calls == []
    update_auto.write_settings(home, {"auto_check": True})
    line = update_auto.notice(home, "1.0.0", lambda: "2.0.0", now=10 ** 9)
    assert "2.0.0 is out" in line
    assert update_auto.notice(home, "1.0.0", lambda: "2.0.0", now=10 ** 9 + 60) is None  # a week
    assert update_auto.notice(home, "2.0.0", lambda: "2.0.0", now=10 ** 9 + 8 * 86400) is None


def test_offline_check_is_silent(tmp_path):
    update_auto.write_settings(str(tmp_path), {"auto_check": True})

    def boom():
        raise OSError("offline")
    assert update_auto.notice(str(tmp_path), "1.0.0", boom) is None


def test_cli_auto_switch(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(update_auto, "home_dir", lambda: str(tmp_path))
    assert update_cli.main(["--auto", "on"]) == 0
    assert update_auto.read_settings(str(tmp_path))["auto_check"] is True
    update_cli.main(["--auto", "off"])
    assert update_auto.read_settings(str(tmp_path))["auto_check"] is False


def test_apply_when_current_does_nothing(monkeypatch, capsys):
    monkeypatch.setattr(update_cli, "latest_from_pypi", lambda: "0.0.1")
    monkeypatch.setattr(update_auto, "apply", lambda *a: (_ for _ in ()).throw(AssertionError))
    assert update_cli.main(["--apply"]) == 0
    assert "nothing to do" in capsys.readouterr().out
