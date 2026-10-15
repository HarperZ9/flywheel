"""crash_report.py -- a local crash report, written and never sent.

When a `flywheel` command dies with an unhandled exception, the traceback is
written to FLYWHEEL_HOME/crashes/<time>.json with the version, OS and Python,
and the command name. Before it is written, the user's home folder is replaced
by `~`, and the value of every environment variable whose name says key, token,
secret or password is replaced by its name, wherever it appears. The command
prints the report's path and the issue link; sending it is the user's choice.
Nothing leaves the machine.
"""
from __future__ import annotations

import json
import os
import platform
import re
import sys
import time
import traceback
from pathlib import Path

ISSUES_URL = "https://github.com/HarperZ9/flywheel/issues/new/choose"
_SECRET_NAME = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL", re.I)


def redact(text: str, environ=None) -> str:
    env = os.environ if environ is None else environ
    for name, value in env.items():
        if _SECRET_NAME.search(name) and value and len(value) >= 4:
            text = text.replace(value, f"<{name}>")
    home = str(Path.home())
    if home and len(home) > 3:
        text = text.replace(home, "~")
    return text


def write_report(exc: BaseException, command: "str | None", home: "str | None" = None,
                 environ=None) -> Path:
    from harness.cli_version import installed_version
    from harness.lane_workdir import flywheel_home
    base = Path(home) if home else flywheel_home(os.environ if environ is None else environ)
    folder = base / "crashes"
    folder.mkdir(parents=True, exist_ok=True)
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    report = {"schema": "flywheel.crash-report/v1", "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
              "version": installed_version(), "python": platform.python_version(),
              "os": f"{platform.system()} {platform.release()}", "command": command or "",
              "exception": redact(f"{type(exc).__name__}: {exc}", environ),
              "traceback": redact(tb, environ)}
    path = folder / (time.strftime("%Y%m%d-%H%M%S") + f"-{os.getpid()}.json")
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path


def report_and_exit(exc: BaseException, command: "str | None") -> int:
    try:
        path = write_report(exc, command)
    except Exception as e:                      # the report must not hide the crash
        print(f"flywheel crashed ({type(exc).__name__}: {exc}); the crash report could "
              f"not be written ({type(e).__name__})", file=sys.stderr)
        return 70
    print(f"flywheel crashed: {type(exc).__name__}. A report with the traceback is at\n"
          f"  {path}\nNothing was sent. To report it, open {ISSUES_URL} and attach "
          "the file after reading it.", file=sys.stderr)
    return 70
