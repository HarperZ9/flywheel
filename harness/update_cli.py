"""update_cli.py -- `flywheel update`: is a newer Flywheel out, and how to get it.

Running the command is the opt-in: it makes one HTTPS GET to PyPI's JSON API
for flywheel-verify and nothing else, and it never runs on its own. Flywheel
does not replace itself; the command prints the upgrade step for the way this
copy was installed (pip, the Windows app, or a source checkout).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request

PYPI_URL = "https://pypi.org/pypi/flywheel-verify/json"
RELEASES_URL = "https://github.com/HarperZ9/flywheel/releases/latest"


def parse_version(text: str) -> tuple:
    """1.5.1 -> (1, 5, 1); a pre-release tail sorts before the release."""
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)(.*)$", text.strip())
    if not m:
        return ()
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)), 0 if m.group(4) else 1)


def latest_from_pypi(opener=urllib.request.urlopen, timeout: float = 10.0) -> str:
    req = urllib.request.Request(PYPI_URL, headers={"User-Agent": "flywheel-update"})
    with opener(req, timeout=timeout) as resp:
        return str(json.loads(resp.read().decode("utf-8"))["info"]["version"])


def install_kind() -> str:
    from pathlib import Path
    if getattr(sys, "frozen", False):
        return "app"
    if (Path(__file__).resolve().parents[1] / "pyproject.toml").is_file():
        return "source"
    return "pip"


def upgrade_step(kind: str) -> str:
    if kind == "app":
        return f"download the installer from {RELEASES_URL} and run it"
    if kind == "source":
        return "git pull in the checkout, then `python -m pip install -e .`"
    return f'"{sys.executable}" -m pip install --upgrade flywheel-verify'


def check(installed: str, latest: str, kind: str) -> dict:
    newer = bool(parse_version(latest)) and parse_version(latest) > parse_version(installed)
    return {"installed": installed, "latest": latest, "update_available": newer,
            "install_kind": kind, "upgrade": upgrade_step(kind) if newer else ""}


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(prog="flywheel update", description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="same as no flag: check and print")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--apply", action="store_true", help="upgrade now (pip installs)")
    ap.add_argument("--auto", choices=("on", "off"),
                    help="a weekly check when flywheel code starts; it never installs")
    args = ap.parse_args(argv)
    from harness import update_auto
    if args.auto:
        home = update_auto.home_dir()
        settings = update_auto.read_settings(home)
        settings["auto_check"] = args.auto == "on"
        update_auto.write_settings(home, settings)
        print(f"weekly update check {'on' if args.auto == 'on' else 'off'}")
        return 0
    from harness.cli_version import installed_version
    try:
        latest = latest_from_pypi()
    except Exception as e:                      # offline is a normal state, not a crash
        print(f"could not reach PyPI ({e.__class__.__name__}); nothing was changed",
              file=sys.stderr)
        return 1
    result = check(installed_version(), latest, install_kind())
    if args.apply:
        if not result["update_available"]:
            print(f"Flywheel {result['installed']} is current; nothing to do.")
            return 0
        ok, message = update_auto.apply(latest, result["install_kind"])
        print(message, file=sys.stdout if ok else sys.stderr)
        return 0 if ok else 1
    if args.json:
        print(json.dumps(result, indent=2))
    elif result["update_available"]:
        print(f"Flywheel {result['latest']} is out; this is {result['installed']}.")
        print(f"To upgrade: {result['upgrade']}")
    else:
        print(f"Flywheel {result['installed']} is current (latest on PyPI: {result['latest']}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
