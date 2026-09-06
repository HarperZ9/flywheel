"""machine_policy.py -- the settings an administrator pins for everyone.

Flywheel's security answers are read from the environment, which is right for a
tool the operator owns and wrong for a machine the operator shares. An
environment variable is set by whoever starts the process, so a standing "no"
can be turned into a "yes" by the account it was meant to constrain. This
module reads a file only an administrator could have written and lets it
outrank both the environment and any user configuration.

Three cases, and they are deliberately not the same:

  absent          nothing is pinned, and the environment decides. A host nobody
                  configured is the ordinary case, not a failure.
  present, unowned  the file is ignored and the reason is carried on the
                  result. Anyone could have dropped it, so obeying it would
                  hand the pin to whoever wrote it.
  present, broken   every pinnable key takes its restrictive value. An
                  administrator's file that cannot be read is not the same as
                  no administrator, and letting a typo fall through to a
                  permissive environment variable would make a malformed policy
                  weaker than none.

An unknown key is broken. It is how a policy is misspelled, and the misspelled
half of `allow_unsandbox: false` is exactly the half that was meant to say no.

Known limits. On Windows the accepted owners are the Administrators group and
SYSTEM; a file owned by the built-in Administrator account or by a domain
administrator is refused rather than trusted, which costs a real deployment a
false refusal and is the direction to be wrong in. Nothing here signs the file,
so an administrator who can write the path is the whole of the trust model.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .machine_policy_owner import owner_problem

__all__ = ["PINNABLE", "Policy", "load_policy", "policy_path"]

#: Every setting an administrator may pin, and the value that is refused to
#: nobody. A key is added here in the same commit as the code that reads it,
#: so a policy file can never pin something the engine does not act on.
PINNABLE: dict = {
    #: Whether a host with no OS-enforced sandbox may run a command bare and
    #: labelled. False is the shipped default and the restrictive value.
    "allow_unsandboxed": False,
}


@dataclass(frozen=True)
class Policy:
    """What an administrator pinned, where it was read, and what went wrong.

    `problem` is carried rather than raised. A policy that could not be trusted
    is a fact about the host worth surfacing to the operator, and an exception
    at import time would take out an engine that runs correctly without any
    policy at all.
    """

    pins: dict = field(default_factory=dict)
    path: str | None = None
    problem: str | None = None

    def pinned(self, key: str):
        """The pinned value for `key`, or None when nothing pinned it."""
        return self.pins.get(key)


def policy_path(platform: str | None = None,
                environ: "dict | os._Environ | None" = None) -> Path:
    """Where this platform keeps settings only an administrator can write.

    Each is a location that already requires elevation to write, so the path
    carries the authority and this module only checks that it was honoured.
    """
    plat = platform if platform is not None else sys.platform
    env = environ if environ is not None else os.environ
    if plat == "win32":
        base = env.get("ProgramData") or r"C:\ProgramData"
        return Path(base) / "flywheel" / "policy.json"
    if plat == "darwin":
        return Path("/Library/Application Support/flywheel/policy.json")
    return Path("/etc/flywheel/policy.json")


def _validate(raw) -> "tuple[dict, str | None]":
    """The pins a document asks for, or the reason it is not a policy."""
    if not isinstance(raw, dict):
        return {}, f"policy is {type(raw).__name__}, not an object"
    unknown = sorted(set(raw) - set(PINNABLE))
    if unknown:
        return {}, f"unknown key(s): {', '.join(unknown)}"
    pins = {}
    for key, value in raw.items():
        want = type(PINNABLE[key])
        if not isinstance(value, want) or isinstance(value, bool) != (
                want is bool):
            return {}, (f"{key} is {type(value).__name__}, "
                        f"expected {want.__name__}")
        pins[key] = value
    return pins, None


def load_policy(path: "Path | str | None" = None, *,
                platform: str | None = None,
                environ: "dict | os._Environ | None" = None,
                owner: "callable | None" = None) -> Policy:
    """Read the machine-wide policy, refusing anything it cannot vouch for.

    `owner` overrides the ownership check so the three cases above are testable
    without an administrator, and without a test that only runs on one OS.
    """
    plat = platform if platform is not None else sys.platform
    target = Path(path) if path is not None else policy_path(plat, environ)
    check = owner if owner is not None else (
        lambda p: owner_problem(p, platform=plat))
    if not target.exists():
        return Policy()
    for candidate in (target, target.parent):
        problem = check(candidate)
        if problem:
            return Policy(path=str(target),
                          problem=f"ignored, {candidate.name}: {problem}")
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return Policy(pins=dict(PINNABLE), path=str(target),
                      problem=f"unreadable, every setting pinned closed: {exc}")
    pins, problem = _validate(raw)
    if problem:
        return Policy(pins=dict(PINNABLE), path=str(target),
                      problem=f"invalid, every setting pinned closed: {problem}")
    return Policy(pins=pins, path=str(target))
