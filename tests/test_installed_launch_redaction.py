"""The installed-launch receipt names no local account and no local path.

Acceptance audit, section 4, and the 1.1.0 security review, finding 8: the
redactor matched the install root in any letter case but replaced it only in
the case it was given, so a value holding the root in other letters came back
whole, user folder included. Registry strings passed through, so the
``Inno Setup: User`` value recorded the Windows account that ran the
installer. A drive path that did not start the value (a quoted command line)
was kept.
"""
from __future__ import annotations

from desktop.tool import installed_launch_acceptance as ila
from tests.installed_launch_acceptance_fixtures import FakeWindows, make_install, row, run_harness

H06 = "H06_uninstall_registry_appid_singleton_or_access_denied"
ACCOUNT = "alice-example"


def _observed(tmp_path, monkeypatch, values):
    for name in ("LOGNAME", "USER", "LNAME", "USERNAME"):
        monkeypatch.setenv(name, ACCOUNT)
    install, _, _ = make_install(tmp_path)
    registry = ila.MetadataResult("PASS", {"InstallLocation": str(install), **values(install)})
    receipt = run_harness(tmp_path, install, windows=FakeWindows(registry=registry))
    return install, row(receipt, H06)["observed_redacted"]


def test_the_install_root_is_replaced_in_any_letter_case(tmp_path, monkeypatch):
    install, observed = _observed(tmp_path, monkeypatch, lambda root: {
        "DisplayIcon": str(root).upper() + "\\flywheel_desktop.exe",
        "UninstallString": '"' + str(root).lower() + '\\unins000.exe"'})
    for key in ("DisplayIcon", "UninstallString"):
        assert str(install).lower() not in observed[key].lower(), observed[key]
        assert "<install_root>" in observed[key]


def test_the_installer_account_and_the_current_user_name_are_masked(tmp_path, monkeypatch):
    _install, observed = _observed(tmp_path, monkeypatch, lambda _root: {
        "Inno Setup: User": ACCOUNT, "Publisher": ACCOUNT.upper(), "DisplayName": "Flywheel"})
    assert observed["Inno Setup: User"] == "<user>"
    assert observed["Publisher"] == "<user>"
    assert observed["DisplayName"] == "Flywheel"


def test_a_drive_path_inside_a_value_is_redacted(tmp_path, monkeypatch):
    _install, observed = _observed(tmp_path, monkeypatch, lambda _root: {
        "ModifyPath": '"C:\\Users\\alice-example\\Downloads\\setup.exe" /modify'})
    assert "alice-example" not in observed["ModifyPath"]
    assert "Users" not in observed["ModifyPath"]
    assert observed["ModifyPath"].endswith("/modify")
