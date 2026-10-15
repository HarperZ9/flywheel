"""streaming_spawn.py -- run a sandbox command with its output in files and a stop flag.

The POSIX sandbox normally runs a command to its end and returns its output.
A background job needs two more things: output it can read while the command
runs, and a way to stop it early. This runner writes stdout and stderr to
stdout.txt and stderr.txt in the run's scratch folder (the same names the
Windows sandbox uses), checks a cancel flag every 250 ms, and on cancel ends
the whole process group (SIGTERM, then SIGKILL after 5 s). Exit 130 means
stopped, 124 timed out.
"""
from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

SLICE = 0.25


def _stop(proc: subprocess.Popen) -> None:
    if os.name == "nt":
        proc.kill()
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(5)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def make_runner(work, cancel=None):
    """A posix_sandbox runner: (argv, root, env, timeout) -> (rc, output)."""
    work = Path(work)

    def run(argv: list, root, env: dict, timeout_seconds: int) -> tuple:
        out_path, err_path = work / "stdout.txt", work / "stderr.txt"
        with open(out_path, "w", encoding="utf-8") as out, open(err_path, "w", encoding="utf-8") as err:
            try:
                proc = subprocess.Popen(argv, cwd=str(root), env=env, stdout=out, stderr=err,
                                        text=True, start_new_session=(os.name != "nt"))
            except OSError as exc:
                return 126, f"[sandbox failed to start] {type(exc).__name__}: {exc}"
            deadline = time.monotonic() + timeout_seconds
            rc = None
            while rc is None:
                if cancel is not None and cancel.is_set():
                    _stop(proc)
                    rc = 130
                    break
                if time.monotonic() >= deadline:
                    _stop(proc)
                    rc = 124
                    break
                try:
                    rc = proc.wait(SLICE)
                except subprocess.TimeoutExpired:
                    rc = None
        text = "\n".join(p.read_text(encoding="utf-8", errors="replace").strip()
                         for p in (out_path, err_path) if p.exists())
        return rc, text.strip()
    return run
