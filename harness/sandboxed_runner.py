"""Sandboxed shell execution: low-integrity isolation with output capture.

Routes shell commands through the Windows low-integrity sandbox. Commands
that shell_admission classifies as dangerous are refused before any process
is created. Non-Windows hosts fail closed with SandboxUnavailable rather
than silently falling back to bare subprocess. Bound credential values are
scrubbed from captured output before it is returned, so a child process
that echoes its own environment cannot leak a secret back to the caller.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from .credential_handles import CredentialBindings
from .shell_admission import Decision, classify_command

__all__ = ["SandboxUnavailable", "sandboxed_run"]


class SandboxUnavailable(RuntimeError):
    """The host cannot provide OS-enforced sandboxed execution."""


def sandboxed_run(
    cmd: str,
    root: str,
    *,
    bindings: CredentialBindings | None = None,
    timeout_seconds: int = 120,
) -> tuple[bool, str]:
    """Run `cmd` under the Windows low-integrity sandbox, rooted at `root`.

    Returns (ok, output). `ok` is False for a denied command, a timeout, or a
    non-zero exit code. Raises SandboxUnavailable when the host cannot
    provide the sandbox at all (non-Windows, or containment setup failed) --
    an honest null rather than a silent fallback to bare subprocess.
    """
    admission = classify_command(cmd)
    if admission.decision == Decision.BLOCK:
        return False, f"[blocked] command denied: {admission.reason_code}"
    if admission.decision == Decision.ESCALATE:
        return False, (f"[denied] command requires escalation: "
                       f"{admission.reason_code}")
    if os.name != "nt":
        raise SandboxUnavailable(
            "sandboxed execution requires Windows low-integrity")

    source = Path(root).resolve()
    work = Path(tempfile.mkdtemp(prefix="fw_sandbox_", dir=source.parent))
    stdout_path, stderr_path = work / "stdout.txt", work / "stderr.txt"
    try:
        rc = _execute(source, work, cmd, _build_env(bindings),
                     timeout_seconds, stdout_path, stderr_path)
        out = _redact(_read_output(stdout_path, stderr_path), bindings)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    if rc == 124:
        return False, f"[timeout after {timeout_seconds}s]\n{out}"
    return rc == 0, f"[exit {rc}]\n{out}"


def _execute(source: Path, work: Path, cmd: str, env: dict[str, str],
             timeout_seconds: int, stdout_path: Path, stderr_path: Path) -> int:
    """Enter the low-integrity namespace and run `cmd` inside it.

    Raises SandboxUnavailable (never the lower-level
    ExecutionInputProtectionUnavailable) when containment cannot be
    established -- an honest null, not a silent fallback.
    """
    from .execution_input_protection import (
        ExecutionInputProtectionUnavailable, protect_execution_namespace,
    )
    argv = [os.environ.get("COMSPEC", "cmd.exe"), "/c", cmd]
    argv[0] = str(Path(argv[0]).resolve())
    try:
        with protect_execution_namespace(source, work) as runner:
            return runner.run(
                argv, env=env, timeout_seconds=timeout_seconds,
                stdout_path=stdout_path, stderr_path=stderr_path)
    except ExecutionInputProtectionUnavailable as e:
        raise SandboxUnavailable(str(e)) from e


def _build_env(bindings: CredentialBindings | None) -> dict[str, str]:
    if bindings is not None:
        return bindings.child_environment(os.environ, platform="windows")
    allowed = ("PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC",
               "TEMP", "TMP")
    return {k: os.environ[k] for k in allowed
            if type(os.environ.get(k)) is str}


def _read_output(stdout_path: Path, stderr_path: Path) -> str:
    parts = []
    for path in (stdout_path, stderr_path):
        try:
            text = path.read_text(encoding="utf-8", errors="replace").strip()
            if text:
                parts.append(text)
        except OSError:
            pass
    return "\n".join(parts)


def _redact(text: str, bindings: CredentialBindings | None) -> str:
    """Scrub every bound credential value out of captured output.

    A sandboxed command legitimately receives its bound secrets in its own
    environment (that is the point of `bindings`), but a value that reaches
    the OUTPUT the caller sees is a leak: it can end up in logs, receipts,
    or an agent's own context. Blanket substitution, not a denylist.
    """
    if bindings is None:
        return text
    for value in bindings._values.values():
        if value:
            text = text.replace(value, "[REDACTED]")
    return text
