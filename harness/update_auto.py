"""update_auto.py -- `flywheel update --apply` and the opt-in weekly check.

`--apply` upgrades a pip or installer-script install in place by running this
interpreter's pip for the exact latest version; the Windows app and a source
checkout are told what to do instead, since replacing those is the user's
step. `--auto on` turns on a check at the start of `flywheel code`, at most once
a week, with a 2-second limit, that prints one line when a newer release exists
and never installs anything. The setting lives in FLYWHEEL_HOME/update.json.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

WEEK = 7 * 24 * 3600


def _settings_path(home: str) -> Path:
    return Path(home) / "update.json"


def read_settings(home: str) -> dict:
    try:
        return json.loads(_settings_path(home).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_settings(home: str, data: dict) -> None:
    path = _settings_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def apply(latest: str, kind: str, run=subprocess.run) -> "tuple[bool, str]":
    if kind != "pip":
        from harness.update_cli import upgrade_step
        return False, f"this install upgrades by hand: {upgrade_step(kind)}"
    p = run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
             "--upgrade", f"flywheel-verify=={latest}"], capture_output=True, text=True,
            timeout=600)
    if p.returncode != 0:
        return False, "pip could not upgrade: " + (p.stderr or p.stdout).strip()[-400:]
    return True, f"upgraded to {latest}"


def notice(home: str, installed: str, fetch, now=None) -> "str | None":
    """One line when auto-check is on, a week has passed and a newer release exists."""
    settings = read_settings(home)
    if not settings.get("auto_check"):
        return None
    now = now or time.time()
    if now - float(settings.get("last_check", 0)) < WEEK:
        return None
    settings["last_check"] = now
    write_settings(home, settings)
    try:
        latest = fetch()
    except Exception:                          # offline: say nothing this week
        return None
    from harness.update_cli import parse_version
    if parse_version(latest) > parse_version(installed):
        return f"Flywheel {latest} is out (this is {installed}); `flywheel update --apply` upgrades."
    return None


def home_dir() -> str:
    from harness.lane_workdir import flywheel_home
    return str(flywheel_home(os.environ))
