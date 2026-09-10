"""In-process startup retains selected roots and explicit argument overrides."""
import pytest

from harness import cli_entry as cli
from harness import gateway


@pytest.mark.parametrize("options,explicit_root", [
    ([], None), (["--root", "explicit"], "explicit"),
    (["--root=equals"], "equals"), (["--roo", "abbreviated"], "abbreviated"),
])
def test_selected_checkout_root_and_user_override(monkeypatch, tmp_path, options,
                                                  explicit_root):
    selected = tmp_path / "selected"
    monkeypatch.setattr(cli, "find_repo_root", lambda: selected)
    monkeypatch.setattr(cli.sys, "frozen", False, raising=False)
    monkeypatch.setattr(cli.os, "chdir", lambda path: None)
    monkeypatch.setattr(gateway, "REPO", tmp_path / "imported-package")
    monkeypatch.setenv("FLYWHEEL_RUN_ROOT", str(tmp_path / "configured-run"))
    seen = []
    monkeypatch.setattr(gateway, "main",
                        lambda argv: seen.append(gateway._build_parser().parse_args(argv)) or 0)
    assert cli._launch_gateway(["--port", "12345", *options]) == 0
    assert seen[0].root == (explicit_root or str(selected))
    assert seen[0].port == 12345
    assert seen[0].run_root == str(tmp_path / "configured-run")


def test_explicit_run_root_overrides_configured_default(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "find_repo_root", lambda: tmp_path)
    monkeypatch.setattr(cli.sys, "frozen", False, raising=False)
    monkeypatch.setattr(cli.os, "chdir", lambda path: None)
    monkeypatch.setenv("FLYWHEEL_RUN_ROOT", "configured")
    seen = []
    monkeypatch.setattr(gateway, "main",
                        lambda argv: seen.append(gateway._build_parser().parse_args(argv)) or 0)
    assert cli._launch_gateway(["--run-root", "explicit-run"]) == 0
    assert seen[0].run_root == "explicit-run"
