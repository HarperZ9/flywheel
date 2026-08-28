"""Bridge between ToolExecutor and the sandboxed/unsandboxed execution paths.

make_sandboxed_runner() returns a callable with the signature
(cmd: str, root: str) -> tuple[bool, str] that local_tools.py's ToolExecutor
accepts as its `runner` callback. On Windows, it routes through the
low-integrity sandbox. Where the sandbox is unavailable, it fails OPEN with
disclosure: output is prefixed `[UNVERIFIABLE: sandbox unavailable] ` rather
than reading like a verified sandboxed result. make_unsandboxed_runner()
provides bare subprocess execution unconditionally, marked `[unsandboxed] `
for the same reason.
"""
from __future__ import annotations

import subprocess
from typing import Callable

from .credential_handles import CredentialBindings

RunnerFn = Callable[[str, str], "tuple[bool, str]"]


def make_sandboxed_runner(
    *, bindings: CredentialBindings | None = None,
    timeout_seconds: int = 120,
) -> RunnerFn:
    def _run(cmd: str, root: str) -> tuple[bool, str]:
        from .sandboxed_runner import SandboxUnavailable, sandboxed_run
        try:
            return sandboxed_run(
                cmd, root, bindings=bindings,
                timeout_seconds=timeout_seconds)
        except SandboxUnavailable:
            # Fail OPEN with disclosure, not silently: mark the output so
            # downstream code (and a human) can tell this call never saw
            # OS-enforced isolation, instead of reading like a normal
            # sandboxed result.
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
