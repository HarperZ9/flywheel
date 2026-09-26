"""The bundled lane child's environment: base names, home, UTF-8, Git and grants.

A frozen build launches each payload lane as a self-child with a small fixed
environment. These tests pin what that environment now carries (the Flywheel
home, UTF-8 stdio, the Git folder when one is found, the lane's declared names
and the operator's env_allow grant) and what it never carries (ungranted
key-shaped names, an injected import path).
"""
from pathlib import Path

import pytest

from harness.lanes_registry import LANES
from harness.mcp_client import LaunchSpec

FAKE = "planted-fake-key-value-0123456789"
_BASE_NT = {
    "SYSTEMROOT": "C:/Windows", "WINDIR": "C:/Windows",
    "COMSPEC": "C:/Windows/System32/cmd.exe", "PATHEXT": ".COM;.EXE",
    "SYSTEMDRIVE": "C:", "TEMP": "D:/t", "TMP": "D:/t", "PATH": "D:/shadow",
}


def _bundled(lane: str, env: dict) -> LaunchSpec:
    return LaunchSpec(("D:/app/flywheel-gateway.exe", "--bundled-lane-mcp", lane),
                      env_overrides=tuple(sorted(env.items())),
                      inherit_env=False, hide_window=True,
                      allowed_tools=(f"{lane}.status", f"{lane}.doctor"))


def test_bundled_env_carries_home_and_utf8(tmp_path):
    from harness.bundled_lane_env import bundled_child_environment

    home = tmp_path / "home"
    env = bundled_child_environment(
        {**_BASE_NT, "FLYWHEEL_HOME": str(home)}, platform="nt", git_dir=None)
    assert env["FLYWHEEL_HOME"] == str(home.resolve())
    assert env["PYTHONUTF8"] == "1"
    assert env["PYTHONIOENCODING"] == "utf-8"
    assert env["PATH"] == "C:/Windows/System32"


def test_bundled_env_drops_key_shaped_names_and_import_path():
    from harness.bundled_lane_env import bundled_child_environment

    env = bundled_child_environment({
        **_BASE_NT, "PYTHONPATH": "D:/malicious", "OPENAI_API_KEY": FAKE,
        "ANTHROPIC_API_KEY": FAKE, "RELAY_SESSION_DIR": "D:/private",
    }, platform="nt", git_dir=None)
    assert FAKE not in repr(env)
    assert "PYTHONPATH" not in env
    assert "RELAY_SESSION_DIR" not in env


def test_git_folder_is_appended_to_the_child_path(tmp_path):
    from harness.bundled_lane_env import bundled_child_environment

    git_dir = tmp_path / "Git" / "cmd"
    env = bundled_child_environment(_BASE_NT, platform="nt", git_dir=str(git_dir),
                                    lane="index")
    assert env["PATH"] == "C:/Windows/System32;" + str(git_dir)


def _fake_git(folder: Path) -> Path:
    folder.mkdir(parents=True)
    exe = folder / "git.exe"
    exe.write_bytes(b"")
    return exe


def test_git_discovery_order_and_none_override(tmp_path):
    from harness.bundled_lane_env import git_directory

    pinned = _fake_git(tmp_path / "pinned")
    program = _fake_git(tmp_path / "pf" / "Git" / "cmd")
    user_git = _fake_git(tmp_path / "user" / "Git" / "cmd")

    def registry(scope):
        return str(user_git.parent) if scope == "user" else None

    def none(_scope):
        return None

    env = {"PATH": "Q", "PROGRAMFILES": str(tmp_path / "pf")}
    assert git_directory({**env, "FLYWHEEL_GIT": str(pinned)}, platform="nt",
                         read_registry_path=registry) == str(pinned.parent)
    assert git_directory({**env, "FLYWHEEL_GIT": "none"}, platform="nt",
                         read_registry_path=registry) is None
    assert git_directory(env, platform="nt", read_registry_path=registry) == str(
        user_git.parent)
    assert git_directory(env, platform="nt", read_registry_path=none) == str(program.parent)
    assert git_directory({"PATH": "Q"}, platform="nt", read_registry_path=none) is None
    assert git_directory({"FLYWHEEL_GIT": str(tmp_path / "missing.exe")}, platform="nt",
                         read_registry_path=none) is None


def test_confined_bundled_launch_gets_declared_granted_and_workdir(tmp_path):
    """Granted names reach the bundled child; ungranted key names never do."""
    from harness.lane_env import confine_lane_launch

    home = tmp_path / "home"
    environ = {**_BASE_NT, "FLYWHEEL_HOME": str(home), "EXAMPLE_API_KEY": FAKE,
               "OTHER_API_KEY": "ungranted-" + FAKE, "MNEME_GATHER_SRC": "D:/g"}
    launch = _bundled("mneme", {"PATH": "C:/Windows/System32", "PYTHONUTF8": "1"})
    confined, codes = confine_lane_launch(
        LANES["mneme"], launch, environ, {"env_allow": ["EXAMPLE_API_KEY"]})
    env = dict(confined.env_overrides)
    folder = home.resolve() / "lanes" / "mneme"
    assert codes == ()
    assert env["EXAMPLE_API_KEY"] == FAKE
    assert env["MNEME_GATHER_SRC"] == "D:/g"
    assert "OTHER_API_KEY" not in env
    assert env["PATH"] == "C:/Windows/System32"
    assert env["MNEME_STATE"] == str(folder / "mneme.db")
    assert confined.cwd == str(folder) and folder.is_dir()
    assert confined.allowed_tools == launch.allowed_tools
    assert confined.inherit_env is False


def test_a_granted_name_never_replaces_a_bundled_base_name(tmp_path):
    from harness.lane_env import confine_lane_launch

    launch = _bundled("gather", {"PATH": "C:/Windows/System32"})
    confined, _ = confine_lane_launch(
        LANES["gather"], launch,
        {**_BASE_NT, "FLYWHEEL_HOME": str(tmp_path)}, {"env_allow": ["PATH"]})
    assert dict(confined.env_overrides)["PATH"] == "C:/Windows/System32"


def test_admission_uses_the_bundled_env(tmp_path):
    from harness import bundled_lane_admission as admission
    from tests.test_bundled_lane_generalization import _rows

    result = admission.admit_bundled_lane(
        "widget", executable="D:/app/flywheel-gateway.exe",
        environ={**_BASE_NT, "FLYWHEEL_HOME": str(tmp_path),
                 "OPENAI_API_KEY": FAKE},
        importable_fn=lambda name: name == "widget.mcp",
        manifest_rows=_rows("widget"))
    env = dict(result.launch.env_overrides)
    assert env["PYTHONUTF8"] == "1"
    assert env["FLYWHEEL_HOME"] == str(tmp_path.resolve())
    assert FAKE not in repr(env)


def test_restricted_launch_joins_a_bound_slot_into_the_bundled_env(tmp_path):
    """R7: a bound slot joins the bundled env instead of replacing it."""
    from harness.credential_handles import CredentialBindings
    from harness.plugin_launch import _restricted_launch

    own = {"PATH": "C:/Windows/System32", "PYTHONUTF8": "1",
           "FLYWHEEL_HOME": str(tmp_path)}
    launch = LaunchSpec(_bundled("forum", own).argv, str(tmp_path),
                        tuple(sorted(own.items())), False, hide_window=True,
                        allowed_tools=("forum.status",))
    bound = _restricted_launch(launch, CredentialBindings({"EXAMPLE_API_KEY": FAKE}),
                               ("EXAMPLE_API_KEY",), lane=True)
    env = dict(bound.env_overrides)
    assert env == {**own, "EXAMPLE_API_KEY": FAKE}
    assert bound.cwd == str(tmp_path)
    assert bound.allowed_tools == ("forum.status",)
    assert bound.hide_window is True and bound.inherit_env is False


def test_restricted_launch_refuses_a_slot_the_bindings_lack(tmp_path):
    from harness.credential_handles import CredentialBindings
    from harness.plugin_launch import PluginPermissionError, _restricted_launch

    launch = _bundled("forum", {"PATH": "C:/Windows/System32"})
    with pytest.raises(PluginPermissionError):
        _restricted_launch(launch, CredentialBindings({}), ("EXAMPLE_API_KEY",),
                           lane=True)


def test_unbound_bundled_launch_still_passes_through_unchanged():
    from harness.credential_handles import CredentialBindings
    from harness.plugin_launch import _restricted_launch

    launch = _bundled("forum", {"PATH": "C:/Windows/System32", "PYTHONUTF8": "1"})
    assert _restricted_launch(launch, CredentialBindings({}), (), lane=True) is launch
