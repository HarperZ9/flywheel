"""The home path guard holds for Windows device, NT-object and UNC spellings.

``os.path.realpath`` keeps a ``\\\\?\\`` or UNC prefix, so a string prefix test
read ``\\\\?\\C:\\<home>\\state\\secret.json`` as outside the Flywheel home and
let a T1 read reach ``state/``, ``keys/`` and the gateway token. A remote UNC
value opened an SMB session with no network grant. The guard now refuses any
value that starts with two separators or ``\\??\\`` on Windows, and decides
containment by folder identity as well as by string. The local-model folder
setting applies the same rule.
"""
from __future__ import annotations

import os

import pytest

from harness.lane_tier_gate import argument_refusal
from harness.path_identity import device_or_unc, inside

windows_only = pytest.mark.skipif(os.name != "nt", reason="Windows path spellings")


@pytest.fixture()
def home(tmp_path, monkeypatch):
    root = tmp_path / "home"
    (root / "state").mkdir(parents=True)
    (root / "state" / "secret.json").write_text("{}", encoding="utf-8")
    (root / "lanes" / "gather").mkdir(parents=True)
    (root / "lanes" / "gather" / "doc.md").write_text("# doc", encoding="utf-8")
    monkeypatch.setenv("FLYWHEEL_HOME", str(root))
    return root


def _spellings(home_path) -> list[str]:
    plain = str(home_path / "state" / "secret.json")
    drive, rest = os.path.splitdrive(plain)
    share = f"{drive[0]}$" if drive else ""
    return [
        "\\\\?\\" + plain,
        "\\\\?\\GLOBALROOT\\??\\" + plain,
        "\\??\\" + plain,
        f"\\\\localhost\\{share}{rest}",
        f"\\\\?\\UNC\\localhost\\{share}{rest}",
        f"//localhost/{share}{rest.replace(os.sep, '/')}",
        "\\\\attacker.invalid\\share\\doc.md",
        "  \\\\?\\" + plain,
    ]


def _refused(value: str) -> bool:
    refusal = argument_refusal("gather", "gather.docs", {"path": value})
    return bool(refusal) and refusal["reason"] == "argument_refused"


@windows_only
def test_every_device_and_unc_spelling_is_refused(home):
    for value in _spellings(home):
        assert _refused(value), value


def test_plain_forms_keep_their_answers(home, tmp_path):
    assert _refused(str(home / "state" / "secret.json"))
    assert _refused(str(home / "lanes" / ".." / "state" / "secret.json"))
    assert not _refused(str(home / "lanes" / "gather" / "doc.md"))
    assert not _refused("doc.md")
    outside = tmp_path / "work" / "notes.md"
    outside.parent.mkdir()
    outside.write_text("x", encoding="utf-8")
    assert not _refused(str(outside))


def test_device_or_unc_is_a_windows_rule():
    assert device_or_unc("\\\\?\\C:\\x", windows=True)
    assert device_or_unc("//server/share", windows=True)
    assert device_or_unc("\\??\\C:\\x", windows=True)
    assert not device_or_unc("C:\\x", windows=True)
    assert not device_or_unc("\\x\\y", windows=True)
    assert not device_or_unc("//server/share", windows=False)


@windows_only
def test_inside_follows_identity_through_a_device_spelling(home):
    target = "\\\\?\\" + str(home / "state" / "secret.json")
    assert inside(target, str(home))
    assert not inside(target, str(home / "lanes" / "gather"))


@windows_only
@pytest.mark.parametrize("form", ["device", "share"])
def test_the_local_model_folder_refuses_the_home_in_any_spelling(home, form):
    from harness.local_agent_grants import GrantRefusal, grants_from_config
    plain = str(home / "state")
    drive, rest = os.path.splitdrive(plain)
    value = "\\\\?\\" + plain if form == "device" else f"\\\\localhost\\{drive[0]}${rest}"
    with pytest.raises(GrantRefusal) as refused:
        grants_from_config({"FLYWHEEL_HOME": str(home)}, workspace=value)
    assert refused.value.code == "WORKSPACE_PROTECTED"


@windows_only
def test_a_run_root_in_a_device_spelling_is_refused(home, tmp_path):
    from harness.local_agent_grants import GrantRefusal, grants_from_config, resolve_run
    work = tmp_path / "work"
    work.mkdir()
    grants = grants_from_config({"FLYWHEEL_HOME": str(home)}, workspace=str(work))
    with pytest.raises(GrantRefusal) as refused:
        resolve_run({"root": "\\\\?\\" + str(work)}, grants, {"FLYWHEEL_HOME": str(home)})
    assert refused.value.code == "INVALID_ROOT"
