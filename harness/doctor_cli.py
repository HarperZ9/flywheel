"""doctor_cli.py -- `flywheel doctor`: is this install ready to work?

One read-only pass over what a first run depends on: the interpreter, the
installed version and how it was installed, the Flywheel home, Git, which
provider keys are set, whether a local model server answers, and whether the
relay coding agent is installed. Each check is OK, WARN or FAIL with the next
step to take. The command exits 1 only when a check FAILs.

A provider key is reported by its variable name only. The value is never read
past "is it non-empty", never printed and never written to the JSON report.
Local servers are probed on loopback with a short timeout; nothing else
leaves the machine.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ISSUES_URL = "https://github.com/HarperZ9/flywheel/issues/new/choose"
KEY_NAMES = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY",
             "DEEPSEEK_API_KEY", "OPENROUTER_API_KEY", "GLM_API_KEY")
LOCAL_SERVERS = (("ollama", "http://127.0.0.1:11434/api/tags"),
                 ("serve.py", "http://127.0.0.1:8765/health"))


def _check(name: str, status: str, detail: str, fix: str = "") -> dict:
    return {"check": name, "status": status, "detail": detail, "fix": fix}


def check_python() -> dict:
    v = sys.version_info
    text = f"{v.major}.{v.minor}.{v.micro} at {sys.executable}"
    if (v.major, v.minor) < (3, 11):
        return _check("python", "FAIL", text, "install Python 3.11 or newer")
    return _check("python", "OK", text)


def check_version() -> dict:
    from harness.cli_version import installed_version
    if getattr(sys, "frozen", False):
        kind = "frozen app build"
    elif (Path(__file__).resolve().parents[1] / "pyproject.toml").is_file():
        kind = "source checkout"
    else:
        kind = "pip install"
    version = installed_version()
    status = "WARN" if version == "unknown" else "OK"
    return _check("flywheel", status, f"{version} ({kind})",
                  "reinstall with `python -m pip install flywheel-verify`"
                  if status == "WARN" else "")


def check_home(environ=None) -> dict:
    from harness.lane_workdir import flywheel_home
    home = flywheel_home(environ if environ is not None else os.environ)
    try:
        home.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=home, prefix=".doctor-", delete=True):
            pass
    except OSError as e:
        return _check("home", "FAIL", f"{home} is not writable ({e.__class__.__name__})",
                      "set FLYWHEEL_HOME to a folder you own")
    return _check("home", "OK", str(home))


def check_git(which=shutil.which, run=subprocess.run) -> dict:
    exe = which("git")
    if not exe:
        return _check("git", "WARN", "not found on PATH",
                      "install Git; checkpoints, auto-commit and the index lane use it")
    try:
        out = run([exe, "--version"], capture_output=True, text=True, timeout=5)
        detail = (out.stdout or "").strip() or exe
    except (OSError, subprocess.SubprocessError):
        detail = exe
    return _check("git", "OK", detail)


def check_keys(environ=None, stored=None) -> dict:
    """Keys by name: from the environment, or stored in the OS credential store."""
    env = environ if environ is not None else os.environ
    if stored is None:
        from harness.keychain import keychain_get
        stored = lambda name: bool(keychain_get(name))  # noqa: E731
    present = [f"{n} (env)" if (env.get(n) or "").strip() else f"{n} (credential store)"
               for n in KEY_NAMES if (env.get(n) or "").strip() or stored(n)]
    if not present:
        return _check("provider keys", "WARN", "none set",
                      "run `flywheel setup` to connect a model, or start a local server")
    return _check("provider keys", "OK", "set: " + ", ".join(present))


def _reachable(url: str, timeout: float) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 (loopback only)
            return 200 <= resp.status < 500
    except (OSError, ValueError):
        return False


def check_local_servers(probe=_reachable, timeout: float = 0.5) -> dict:
    live = [name for name, url in LOCAL_SERVERS if probe(url, timeout)]
    if not live:
        return _check("local models", "WARN", "no local server answered on loopback",
                      "optional: start ollama to work offline")
    return _check("local models", "OK", "answering: " + ", ".join(live))


def check_relay() -> dict:
    from importlib import metadata
    try:
        version = metadata.version("flywheel-relay")
    except metadata.PackageNotFoundError:
        return _check("relay", "WARN", "not installed",
                      "run `flywheel install --lanes relay` for `flywheel relay`")
    return _check("relay", "OK", f"flywheel-relay {version}")


def run_checks(environ=None) -> list[dict]:
    return [check_python(), check_version(), check_home(environ), check_git(),
            check_keys(environ), check_local_servers(), check_relay()]


def render(checks: list[dict]) -> str:
    lines = ["Flywheel doctor"]
    for c in checks:
        lines.append(f"  {c['status']:<4} {c['check']:<14} {c['detail']}")
        if c["fix"]:
            lines.append(f"       {'':<14} next: {c['fix']}")
    fails = sum(c["status"] == "FAIL" for c in checks)
    warns = sum(c["status"] == "WARN" for c in checks)
    lines.append(f"{fails} failed, {warns} warnings. Report a problem: {ISSUES_URL}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="flywheel doctor", description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="print the checks as JSON")
    args = ap.parse_args(argv)
    checks = run_checks()
    if args.json:
        print(json.dumps({"schema": "flywheel.doctor/v1", "checks": checks}, indent=2))
    else:
        print(render(checks))
    return 1 if any(c["status"] == "FAIL" for c in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
