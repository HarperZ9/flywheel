"""Falsifiers for the standalone gateway launcher (harness/cli_entry.py).

A bare `pip install flywheel-verify` ships harness/ but not scripts/. `flywheel
up` and `flywheel app` must start the gateway by importing harness.gateway
directly, never requiring a source checkout. Passthrough commands with no
checkout must fail with a message, not a traceback. When a checkout IS present
(dev), the launcher must still prefer scripts/run_harness_cli.py. When frozen
(PyInstaller exe), the checkout probe must be skipped entirely.
"""
import harness.cli_entry as cli
import harness.gateway as gw


def _record(store):
    """A gateway.main stand-in that records its argv and returns 0 (success)."""
    def _fake(argv):
        store["argv"] = argv
        return 0
    return _fake


def _no_repo():
    raise FileNotFoundError("no checkout")


def test_launch_gateway_uses_package_when_no_checkout(monkeypatch):
    monkeypatch.setattr(cli, "find_repo_root", _no_repo)
    monkeypatch.setattr(cli.sys, "frozen", False, raising=False)
    seen = {}
    monkeypatch.setattr(gw, "main", _record(seen))
    rc = cli._launch_gateway(["--port", "8799"])
    assert rc == 0
    assert seen["argv"] == ["--port", "8799"]


def test_launch_gateway_prefers_checkout_when_present(monkeypatch, tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "run_harness_cli.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    monkeypatch.setattr(cli, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(cli.sys, "frozen", False, raising=False)
    monkeypatch.setattr(cli.os, "chdir", lambda p: None)  # no real cwd change
    ran = {}

    def _fake_runpath(path, run_name=None):
        ran["path"] = path
        ran["argv"] = list(cli.sys.argv)
        raise SystemExit(0)

    monkeypatch.setattr(cli.runpy, "run_path", _fake_runpath)
    rc = cli._launch_gateway(["--port", "8799"])
    assert rc == 0
    assert ran["path"].endswith("run_harness_cli.py")
    assert ran["argv"][1:] == ["app", "--port", "8799"]


def test_launch_gateway_frozen_never_consults_the_checkout(monkeypatch, tmp_path):
    # A frozen exe must run the bundled package even when a checkout exists on
    # disk: find_repo_root would succeed here, so passing proves it is skipped.
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "run_harness_cli.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    monkeypatch.setattr(cli, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(cli.sys, "frozen", True, raising=False)
    seen = {}
    monkeypatch.setattr(gw, "main", _record(seen))
    ran = {"runpy": False}
    monkeypatch.setattr(cli.runpy, "run_path",
                        lambda *a, **k: ran.__setitem__("runpy", True))
    rc = cli._launch_gateway(["--port", "8799"])
    assert rc == 0
    assert seen["argv"] == ["--port", "8799"]
    assert ran["runpy"] is False


def test_app_command_launches_gateway_without_checkout(monkeypatch):
    monkeypatch.setattr(cli, "find_repo_root", _no_repo)
    monkeypatch.setattr(cli.sys, "frozen", False, raising=False)
    seen = {}
    monkeypatch.setattr(gw, "main", _record(seen))
    rc = cli.main(["app", "--port", "8799"])
    assert rc == 0
    assert seen["argv"] == ["--port", "8799"]


def test_app_command_keeps_a_value_that_equals_app(monkeypatch):
    # Only the command token is dropped; a later value spelled "app"
    # (e.g. `--root app`) must survive.
    monkeypatch.setattr(cli, "find_repo_root", _no_repo)
    monkeypatch.setattr(cli.sys, "frozen", False, raising=False)
    seen = {}
    monkeypatch.setattr(gw, "main", _record(seen))
    rc = cli.main(["app", "--root", "app"])
    assert rc == 0
    assert seen["argv"] == ["--root", "app"]


def test_up_command_launches_gateway_without_checkout(monkeypatch):
    monkeypatch.setattr(cli, "find_repo_root", _no_repo)
    monkeypatch.setattr(cli.sys, "frozen", False, raising=False)
    seen = {}
    monkeypatch.setattr(gw, "main", _record(seen))
    rc = cli.main(["up"])
    assert rc == 0
    # _cmd_up injects the exact default port before delegating to the launcher.
    assert seen["argv"] == ["--port", "8799"]


def test_passthrough_without_checkout_fails_gracefully(monkeypatch, capsys):
    monkeypatch.setattr(cli, "find_repo_root", _no_repo)
    monkeypatch.setattr(cli.sys, "frozen", False, raising=False)
    rc = cli.main(["mcp-health"])
    assert rc == 2
    assert "requires a source checkout" in capsys.readouterr().err


def test_bare_invocation_without_checkout_prints_usage(monkeypatch, capsys):
    monkeypatch.setattr(cli, "find_repo_root", _no_repo)
    monkeypatch.setattr(cli.sys, "frozen", False, raising=False)
    rc = cli.main([])
    assert rc == 2
    err = capsys.readouterr().err
    assert "usage: flywheel" in err
    assert "up" in err and "lanes" in err


def test_help_without_checkout_is_a_success(monkeypatch, capsys):
    monkeypatch.setattr(cli, "find_repo_root", _no_repo)
    monkeypatch.setattr(cli.sys, "frozen", False, raising=False)
    rc = cli.main(["--help"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "usage: flywheel" in out
    assert "up" in out and "lanes" in out


def test_lanes_probe_flag_is_forwarded_to_roster(monkeypatch, capsys):
    calls = []
    roster = {"n_lanes": 0, "by_status": {}, "lanes": []}
    monkeypatch.setattr(
        "harness.lanes.lane_roster",
        lambda **kwargs: calls.append(kwargs) or roster,
    )
    monkeypatch.setattr("harness.lanes.lane_report", lambda value: "empty")
    assert cli._dispatch_umbrella("lanes", ["--probe"]) == 0
    assert calls == [{"probe": True}]
