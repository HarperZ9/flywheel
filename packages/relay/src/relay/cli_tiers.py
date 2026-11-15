"""cli_tiers.py -- the doctor's row for each online tier that starts an agent CLI.

A row is PASS only when the tier can run and its isolation is the one the Q0
probes proved: the CLI resolves to an absolute path, the launch grants exec, the
profile is proven, and the installed version is the version the probes tested.
Every other state is WARN with a setup code, so a client can tell "not
installed" from "installed but untested". The doctor starts ``--version`` only
when exec is granted (the tier cannot run otherwise), through the same helper,
and never reports the resolved path.
"""
from __future__ import annotations

import re
import subprocess

from ._vendor import safe_spawn
from .child_env import EXEC_CLI_ENV, cli_allowed, named_cli_grants, profile_proven

_VERSION = re.compile(r"\d+\.\d+\.\d+")
VERSION_TIMEOUT = 15

SETUP = {
    "EXEC_NOT_GRANTED": "start the server with --allow-exec or RELAY_ALLOW_EXEC=1",
    "CLI_NOT_FOUND": "install the CLI, or set its RELAY_<NAME>_CLI to an absolute path",
    "CLI_PROFILE_UNPROVEN": f"no isolation profile is proven for this CLI; {EXEC_CLI_ENV} "
                            "must name it before it starts",
    "CLI_VERSION_UNTESTED": "the isolation profile was proven on another version; rerun "
                            "the probes before relying on it",
    "CLI_VERSION_UNKNOWN": "the CLI did not report a version",
}


def installed_version(name: str, override_var: str | None, runner=None) -> str | None:
    """The first x.y.z the CLI prints for --version, or None."""
    try:
        run = runner or safe_spawn.run
        r = run(name, ["--version"], override_var=override_var, timeout=VERSION_TIMEOUT)
    except (safe_spawn.SpawnRefused, subprocess.SubprocessError, OSError):
        return None
    match = _VERSION.search(f"{r.stdout or ''} {r.stderr or ''}")
    return match.group(0) if match else None


def _row(provider: str, cli: dict, exec_granted: bool, runner) -> dict:
    name, profile, override = cli["argv"][0], cli.get("profile"), cli.get("override")
    prof = safe_spawn.PROFILES.get(profile or "")
    try:
        safe_spawn.resolve(name, override)
        installed = True
    except safe_spawn.SpawnRefused:
        installed = False
    usable = installed and exec_granted and cli_allowed(profile)
    version = installed_version(name, override, runner) if usable else None
    tested = prof.tested if prof else ""
    if not installed:
        setup = "CLI_NOT_FOUND"
    elif not exec_granted:
        setup = "EXEC_NOT_GRANTED"
    elif not profile_proven(profile):
        setup = "CLI_PROFILE_UNPROVEN"
    elif version is None:
        setup = "CLI_VERSION_UNKNOWN"
    elif version != tested:
        setup = "CLI_VERSION_UNTESTED"
    else:
        setup = None
    return {"tier": provider, "cli": name, "profile": profile,
            "profile_proven": profile_proven(profile), "profile_tested": tested,
            "named_grant": (profile or "").lower() in named_cli_grants(),
            "installed": installed, "usable": usable, "version": version,
            "status": "PASS" if setup is None else "WARN", "setup": setup,
            "hint": SETUP.get(setup)}


def cli_tier_rows(exec_granted: bool, runner=None) -> list[dict]:
    """One row per provider that has a CLI tier, in PROVIDERS order."""
    from .endpoints import PROVIDERS
    return [_row(p, spec["cli"], exec_granted, runner)
            for p, spec in PROVIDERS.items() if spec.get("cli")]
