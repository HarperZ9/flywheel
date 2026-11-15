"""The scrubber runs in time linear in its input. A value after a secret-named
key is checked against a path pattern, and a pattern with a nested quantifier
there made a value that starts like a path and later fails (`:ro`, `?`, `=`,
`//`) take time that doubles with each character: import, the store write and
the store backstop hung with no timeout. Each check runs in a child process
under a timeout, so a regression fails here instead of hanging the suite."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import canon

SRC = str(Path(canon.__file__).resolve().parents[1])
SLOW = 1.0  # seconds; the linear pattern takes milliseconds on each input

_TIMER = """
import json, sys, time
from canon.workspace.scrub import find_secrets, scrub
out = []
for text in json.loads(sys.stdin.read()):
    start = time.perf_counter()
    scrub(text)
    find_secrets(text)
    out.append(time.perf_counter() - start)
print(json.dumps(out))
"""


def _child_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = SRC + os.pathsep + env.get("PYTHONPATH", "")
    return env


def _inputs() -> list[str]:
    slash_key = "/LOMyx8SC5w903i2fq" + "/pMMU31LZ//sHSYfMsMNve"
    return [
        "SECRETS=/run/secrets/production_db_pass:ro",
        "token_url: /oauth/authorize_endpoint_app?client_id=abc",
        "KEY_FILE=/home/runner/work/repository_name/keys.pem:ro",
        "TODO: mount ./certs/signing_key.pem:/etc/application/certs/signing_key.pem:ro in compose",
        "AWS_SECRET_ACCESS_KEY=" + slash_key,
        "KEY_PATH=/" + "a" * 5000 + ":ro",
        "db_password: /" + "ab/" * 2000 + "=x",
        "private_key_path: ~/" + "segment_" * 1000 + "?v=1",
        "TOKEN=" + "C:\\" + "dir\\" * 2000 + ":",
    ]


def test_a_path_shaped_value_that_fails_late_is_scrubbed_in_linear_time():
    proc = subprocess.run([sys.executable, "-c", _TIMER], input=json.dumps(_inputs()),
                          capture_output=True, text=True, timeout=60, env=_child_env())
    assert proc.returncode == 0, proc.stderr
    timings = json.loads(proc.stdout)
    slow = {text[:40]: round(t, 2) for text, t in zip(_inputs(), timings) if t > SLOW}
    assert not slow, slow


def _long_runs() -> list[str]:
    """A long name run and a text with many redactions, each of which took
    seconds when a rule re-read the run once per character or re-scanned the
    earlier redactions once per match."""
    return [
        "passwd-" * 4000,
        "key_" * 5000 + "=x",
        "KEY_" * 5000,
        "a." * 20000,
        "x://" * 10000,
        '"' + "token" * 5000,
        "ghp_" + "abcdefgh1234 ghp_" * 16000,
        "?" + "key_" * 5000 + "=x",
        "?" + "a." * 20000 + ":x",
        "A&" * 10000,
        " -" + "-a" * 10000,
    ]


def test_a_long_name_run_and_many_redactions_are_scrubbed_in_linear_time():
    proc = subprocess.run([sys.executable, "-c", _TIMER], input=json.dumps(_long_runs()),
                          capture_output=True, text=True, timeout=120, env=_child_env())
    assert proc.returncode == 0, proc.stderr
    timings = json.loads(proc.stdout)
    slow = {text[:20]: round(t, 2) for text, t in zip(_long_runs(), timings) if t > SLOW}
    assert not slow, slow


def test_the_cli_stores_a_task_that_mounts_a_key_file(tmp_path):
    repo = tmp_path / "r"
    (repo / ".git").mkdir(parents=True)
    (repo / ".git" / "config").write_text(
        '[remote "origin"]\n\turl = https://github.com/o/r\n', encoding="utf-8")
    task = "Mount KEY_FILE=/home/runner/work/repository_name/keys.pem:ro in the job"
    base = ["--workspace", str(repo), "--store", str(tmp_path / "s")]
    proc = subprocess.run([sys.executable, "-m", "canon.cli", "--json", "workspace", "task",
                           task, *base], capture_output=True, text=True, timeout=60,
                          env=_child_env())
    assert proc.returncode == 0, proc.stdout + proc.stderr
    listed = subprocess.run([sys.executable, "-m", "canon.cli", "workspace", "list", *base],
                            capture_output=True, text=True, timeout=60, env=_child_env())
    assert task in listed.stdout
