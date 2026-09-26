"""The two old hook scripts stay one release as thin wrappers: a deprecation
line on stderr, then the capture hook module, which fails loudly."""
import json
import subprocess
import sys
from pathlib import Path

from capture_channel_fixture import hook_env, spool_files, stop_event

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts" / "hooks"


def _run(script, home, cwd):
    return subprocess.run([sys.executable, str(SCRIPTS / script), "--home", str(home)],
                          input=json.dumps(stop_event()).encode(), cwd=str(cwd),
                          env=hook_env(), capture_output=True, timeout=60)


def test_the_old_stop_script_is_loud_and_names_the_module(tmp_path):
    home, work = tmp_path / "home", tmp_path / "work"
    home.mkdir()
    work.mkdir()
    proc = _run("wrapper_turn_receipt_hook.py", home, work)
    lines = proc.stderr.decode().strip().splitlines()
    assert proc.returncode == 1
    assert "deprecated" in lines[0] and "harness.capture_hooks" in lines[0]
    assert "TOKEN_MISSING" in lines[1]
    assert len(spool_files(home)) == 1


def test_the_old_prompt_script_fetches_nothing_and_reports(tmp_path):
    home, work = tmp_path / "home", tmp_path / "work"
    home.mkdir()
    work.mkdir()
    proc = _run("wrapper_scaffold_hook.py", home, work)
    assert proc.returncode == 0
    assert "TOKEN_MISSING" in json.loads(proc.stdout)["systemMessage"]
