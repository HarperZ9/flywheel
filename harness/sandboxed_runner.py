"""Sandboxed shell execution: OS-enforced isolation with output capture.

Routes shell commands through the Windows low-integrity sandbox, and through
bubblewrap or Seatbelt on the two hosts that used to get nothing. Commands
that shell_admission classifies as dangerous are refused before any process
is created. A host with no backend at all still fails closed with
SandboxUnavailable rather than silently falling back to bare subprocess.
Bound credential values are scrubbed from captured output before it is
returned, so a child process that echoes its own environment cannot leak a
secret back to the caller.

The three backends confine the filesystem. They do not all confine the same
things beyond it, so a POSIX run prefixes its output with a line naming the
backend and what it enforced. A command that behaved differently on two
machines is explained by that line or by nothing.
"""
from __future__ import annotations

import os
import shutil
import sys
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
    """Run `cmd` under this host's sandbox, rooted at `root`.

    Returns (ok, output). `ok` is False for a denied command, a timeout, or a
    non-zero exit code. Raises SandboxUnavailable when the host cannot
    provide a sandbox at all (no backend installed, or containment setup
    failed) -- an honest null rather than a silent fallback to bare
    subprocess.
    """
    admission = classify_command(cmd)
    if admission.decision == Decision.BLOCK:
        return False, f"[blocked] command denied: {admission.reason_code}"
    if admission.decision == Decision.ESCALATE:
        return False, (f"[denied] command requires escalation: "
                       f"{admission.reason_code}")
    if os.name != "nt":
        return _posix_sandboxed_run(cmd, root, bindings, timeout_seconds)

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


def _posix_sandboxed_run(
    cmd: str, root: str, bindings: CredentialBindings | None,
    timeout_seconds: int,
) -> tuple[bool, str]:
    """Run `cmd` under whichever POSIX backend this host has.

    Network is left reachable. The Windows backend cannot restrict it, so
    denying it here would make one command succeed on one machine and fail on
    another for a reason no caller asked about. The mechanism defaults the
    other way, and this line is where the parity argument is made rather than
    a default nobody can see. `Confinement.network` records what held.
    """
    from .posix_sandbox import posix_run
    source = Path(root).resolve()
    # Scratch goes to the system temp rather than beside the workspace.
    # The Windows backend needs a sibling for the integrity ACL; these two
    # do not, and a directory appearing next to an operator's repo every
    # time a command runs is a cost with nothing bought by it.
    #
    # Resolved, because the policy is matched against the path the kernel
    # canonicalises to. macOS hands out `/var/folders/...` and resolves it to
    # `/private/var/folders/...`, so an unresolved scratch path would be
    # written into the profile in a spelling nothing ever matches, and the
    # directory the run was told to use would be the one directory it could
    # not write to.
    work = Path(tempfile.mkdtemp(prefix="fw_sandbox_")).resolve()
    env = _build_posix_env(bindings, work)
    try:
        outcome = posix_run(cmd, source, work, env=env,
                            timeout_seconds=timeout_seconds, network=True)
        if outcome is None:
            raise SandboxUnavailable(
                f"no sandbox backend on this host: install bubblewrap "
                f"(linux) or use macOS sandbox-exec; platform={sys.platform}")
        rc, out, plan = outcome
    finally:
        shutil.rmtree(work, ignore_errors=True)
    out = f"{plan.summary()}\n{_redact(out, bindings)}".rstrip()
    if rc == 124:
        return False, f"[timeout after {timeout_seconds}s]\n{out}"
    return rc == 0, f"[exit {rc}]\n{out}"


def _build_posix_env(bindings: CredentialBindings | None,
                     work: Path) -> dict[str, str]:
    """The child's environment, with its temp directory inside the sandbox.

    The allowlist passes the host's `TMPDIR` through, and the host's is
    outside everything the policy makes writable. A toolchain that reads it
    would open a path the kernel refuses, so the value is replaced by the
    scratch directory the backend binds writable. `TMP` and `TEMP` are set
    alongside it because plenty of programs read those instead and one
    unset name is enough to send a temp file somewhere denied.
    """
    active = bindings if bindings is not None else CredentialBindings({})
    env = active.child_environment(os.environ, platform="posix")
    env.update({name: str(work) for name in ("TMPDIR", "TMP", "TEMP")})
    return env


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
    active = bindings if bindings is not None else CredentialBindings({})
    return active.child_environment(os.environ, platform="windows")


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
    return bindings.redact(text)
