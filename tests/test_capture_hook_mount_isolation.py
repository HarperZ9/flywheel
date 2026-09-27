"""The printed hook mount runs Flywheel's hook, never a `harness` package the
project folder happens to hold, and the doctor fails a mount that would let
the project folder or a settings `env` block choose the module."""
import json
import os
import shlex
import subprocess
import sys

import pytest


def _prompt_mount() -> str:
    from harness.trace_doctor import print_mount
    lines = print_mount()
    claude = json.loads(lines[lines.index("Claude Code (settings.json):") + 1])
    return claude["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]


def _plant_fake_harness(project, marker):
    pkg = project / "harness" / "capture_hooks"
    pkg.mkdir(parents=True)
    (project / "harness" / "__init__.py").write_text("")
    (pkg / "__init__.py").write_text("")
    (pkg / "__main__.py").write_text(f"open(r'{marker}', 'w').write('ran')\n")


def _run(command, project, env):
    argv = shlex.split(command, posix=os.name != "nt")
    argv = [a.strip('"') for a in argv]
    return subprocess.run(argv, input=b"{}", cwd=str(project), env=env,
                          capture_output=True, timeout=60)


@pytest.fixture
def project(tmp_path):
    folder = tmp_path / "repo"
    folder.mkdir()
    _plant_fake_harness(folder, tmp_path / "HIJACKED")
    return folder


def test_the_printed_mount_isolates_the_interpreter():
    words = shlex.split(_prompt_mount(), posix=os.name != "nt")
    head = words[1:words.index("-m")]
    assert "-P" in head and "-E" in head


def test_a_harness_package_in_the_project_does_not_replace_the_hook(project, tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith("FLYWHEEL_")}
    env["PYTHONPATH"] = str(project)
    _run(_prompt_mount(), project, env)
    assert not (tmp_path / "HIJACKED").exists()


def test_control_without_the_flags_the_project_package_runs(project, tmp_path):
    """False-success control: the fake package is live, so the test above
    proves the flags, not a broken fixture."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("FLYWHEEL_")}
    bare = f'"{sys.executable}" -m harness.capture_hooks prompt --client claude-code'
    _run(bare, project, env)
    assert (tmp_path / "HIJACKED").read_text() == "ran"


@pytest.mark.parametrize("flags,problem", [
    ("", True), ("-P", True), ("-E", True), ("-P -E", False), ("-I", False),
    ("-PE", False), ("-EP", False)])
def test_the_doctor_fails_a_module_mount_without_isolation(flags, problem):
    from harness.trace_doctor_mounts import classify
    command = f'"{sys.executable}" {flags} -m harness.capture_hooks stop --client codex'
    mount = classify("codex hooks.json", "Stop", command)
    assert mount is not None and mount.form == "module"
    assert ("project folder" in mount.problem) is problem
