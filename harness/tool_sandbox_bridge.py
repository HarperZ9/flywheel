"""Bridge between ToolExecutor and the sandboxed/unsandboxed execution paths.

make_sandboxed_runner() returns a callable with the signature
(cmd: str, root: str) -> tuple[bool, str] that local_tools.py's ToolExecutor
accepts as its `runner` callback. On Windows it routes through the
low-integrity sandbox. Only Windows has that sandbox today, so on macOS and
Linux every call reaches the question of what to do when the isolation the
caller asked for does not exist.

That question is now the caller's, and its default is REFUSE. A command that
cleared shell_admission has cleared a static classifier, which is a different
thing from OS-enforced isolation, and a runner named sandboxed should not
quietly become a bare `subprocess.run(shell=True)` on a platform where the
only signal was a prefix in a string somebody may never read.

`on_unavailable="disclose"` restores the older behaviour for a caller that
wants it: the command runs bare and its output is prefixed
`[UNVERIFIABLE: sandbox unavailable] `. The shipped entry points read that
choice from FLYWHEEL_ALLOW_UNSANDBOXED through fallback_from_env(), so the
escape hatch is one documented variable rather than a default nobody set.

make_unsandboxed_runner() provides bare subprocess execution unconditionally,
marked `[unsandboxed] `, for a caller who is asking for exactly that.
"""
from __future__ import annotations

import os
import subprocess
from typing import Callable, Mapping

from .credential_handles import CredentialBindings

RunnerFn = Callable[[str, str], "tuple[bool, str]"]

#: What a sandboxed runner does on a host with no sandbox.
FALLBACKS = ("refuse", "disclose")

ALLOW_UNSANDBOXED_ENV = "FLYWHEEL_ALLOW_UNSANDBOXED"

_REFUSAL = (
    "[refused] this host provides no OS-enforced sandbox and the caller "
    "asked for one. Set " + ALLOW_UNSANDBOXED_ENV + "=1 to run such commands "
    "bare and labelled, or use make_unsandboxed_runner() to ask for that "
    "outright.")


def fallback_from_env(env: "Mapping[str, str] | None" = None) -> str:
    """Read the operator's standing answer for a host with no sandbox.

    Kept out of the runner itself so the policy is visible at the call site
    rather than resolved somewhere inside a factory. An unset variable means
    refuse, so a host that was never configured is a host that says no.
    """
    raw = (env if env is not None else os.environ).get(
        ALLOW_UNSANDBOXED_ENV, "")
    return "disclose" if raw.strip().lower() in {"1", "true", "yes", "on"} \
        else "refuse"


def make_sandboxed_runner(
    *, bindings: "CredentialBindings | dict[str, str] | None" = None,
    timeout_seconds: int = 120,
    on_unavailable: str = "refuse",
) -> RunnerFn:
    if on_unavailable not in FALLBACKS:
        # A typo in a security policy fails where the policy is written, not
        # on the first command that happens to reach the fallback.
        raise ValueError(
            f"on_unavailable must be one of {FALLBACKS}, got "
            f"{on_unavailable!r}")
    if isinstance(bindings, dict):
        bindings = CredentialBindings(bindings)
    def _run(cmd: str, root: str) -> tuple[bool, str]:
        from .sandboxed_runner import SandboxUnavailable, sandboxed_run
        try:
            return sandboxed_run(
                cmd, root, bindings=bindings,
                timeout_seconds=timeout_seconds)
        except SandboxUnavailable as e:
            if on_unavailable == "refuse":
                return False, f"{_REFUSAL}\n[reason] {e}"
            # Fail OPEN with disclosure: mark the output so downstream code
            # and a human can tell this call never saw OS-enforced isolation,
            # instead of reading like a normal sandboxed result.
            ok, out = _bare_run(
                cmd, root, timeout_seconds,
                prefix="[UNVERIFIABLE: sandbox unavailable] ")
            if bindings is not None:
                out = bindings.redact(out)
            return ok, out
    return _run


def make_unsandboxed_runner(
    *, timeout_seconds: int = 120,
) -> RunnerFn:
    def _run(cmd: str, root: str) -> tuple[bool, str]:
        return _bare_run(cmd, root, timeout_seconds, prefix="[unsandboxed] ")
    return _run


def _bare_run(
    cmd: str, root: str, timeout: int, prefix: str = "",
) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            cmd, shell=True, cwd=root,
            capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        partial = ((e.stdout or "") if isinstance(e.stdout, str)
                   else (e.stdout or b"").decode("utf-8", "replace"))
        partial += ((e.stderr or "") if isinstance(e.stderr, str)
                    else (e.stderr or b"").decode("utf-8", "replace"))
        return False, f"{prefix}[timeout after {timeout}s]\n{partial}"
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, f"{prefix}[exit {proc.returncode}]\n{out}"
