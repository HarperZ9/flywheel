"""The two old hook scripts were removed in 2.0. Each file is a stub: one
line on stderr naming the module to mount, exit 1, and nothing captured. The
doctor reports a mount that still names one as a failure."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from capture_channel_fixture import hook_env, spool_files, stop_event
from harness.trace_doctor_mounts import LEGACY, REMOVED, classify

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts" / "hooks"
CASES = (("wrapper_turn_receipt_hook.py", "stop"), ("wrapper_scaffold_hook.py", "prompt"))


def _run(script, home, cwd):
    return subprocess.run([sys.executable, str(SCRIPTS / script), "--home", str(home)],
                          input=json.dumps(stop_event()).encode(), cwd=str(cwd),
                          env=hook_env(), capture_output=True, timeout=60)


@pytest.mark.parametrize("script,event", CASES)
def test_a_removed_script_fails_and_names_the_module(tmp_path, script, event):
    home, work = tmp_path / "home", tmp_path / "work"
    home.mkdir()
    work.mkdir()
    proc = _run(script, home, work)
    lines = proc.stderr.decode().strip().splitlines()
    assert proc.returncode == 1
    assert len(lines) == 1
    assert "removed in Flywheel 2.0" in lines[0]
    assert f"python -m harness.capture_hooks {event}" in lines[0]
    assert "docs/MIGRATING-2.0.md" in lines[0]
    assert proc.stdout == b""


@pytest.mark.parametrize("script,event", CASES)
def test_a_removed_script_captures_nothing(tmp_path, script, event):
    """Control: the 1.x wrapper spooled the turn it could not send. A stub
    that still forwarded to the module would leave a spool file here."""
    home, work = tmp_path / "home", tmp_path / "work"
    home.mkdir()
    work.mkdir()
    _run(script, home, work)
    assert spool_files(home) == []
    assert list(home.iterdir()) == []


@pytest.mark.parametrize("script,event", CASES)
def test_a_removed_script_imports_no_harness_code(script, event):
    source = (SCRIPTS / script).read_text(encoding="utf-8")
    assert "harness.capture_hooks.__main__" not in source
    assert "import main" not in source


def test_the_stub_list_matches_the_doctor_list():
    assert sorted(LEGACY) == sorted(p.name for p in SCRIPTS.glob("wrapper_*.py"))


@pytest.mark.parametrize("script,event", CASES)
def test_the_doctor_fails_a_mount_that_names_a_removed_script(script, event):
    mount = classify("claude settings.json", "Stop", f'python "{SCRIPTS / script}"')
    assert mount.form == "legacy-script" and mount.problem == REMOVED
    missing = classify("claude settings.json", "Stop", f"python /nowhere/{script}")
    assert missing.problem == REMOVED


def test_the_doctor_still_passes_a_module_mount():
    mount = classify("claude settings.json", "Stop",
                     f'"{sys.executable}" -P -E -m harness.capture_hooks stop')
    assert mount.form == "module" and mount.problem == ""
