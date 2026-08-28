"""Bridge between ToolExecutor and the sandboxed/unsandboxed execution paths.

make_sandboxed_runner() returns a callable with the signature
(cmd: str, root: str) -> tuple[bool, str] that local_tools.py's ToolExecutor
accepts as its `runner` callback. On Windows, it routes through the
low-integrity sandbox. Elsewhere, make_unsandboxed_runner() provides bare
subprocess execution with an honest-null note.
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
            return _bare_run(cmd, root, timeout_seconds)
    return _run


def make_unsandboxed_runner(
    *, timeout_seconds: int = 120,
) -> RunnerFn:
    def _run(cmd: str, root: str) -> tuple[bool, str]:
        return _bare_run(cmd, root, timeout_seconds)
    return _run


def _bare_run(
    cmd: str, root: str, timeout: int,
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
        return False, f"[timeout after {timeout}s]\n{partial}"
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, f"[exit {proc.returncode}]\n{out}"
