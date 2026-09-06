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

    Network is left reachable unless an operator named the hosts a run may
    reach. The Windows backend cannot restrict it, so denying it here by
    default would make one command succeed on one machine and fail on another
    for a reason no caller asked about. The mechanism defaults the other way,
    and this line is where the parity argument is made rather than a default
    nobody can see. `Confinement.network` records what held.

    With `FLYWHEEL_EGRESS_HOSTS` set the run gets a proxy instead, the
    network is denied around it, and every request the run made is in the
    output whether it was carried or refused. A policy that was asked for and
    cannot be routed stops the run. Falling back to the open network there
    would be the one moment the feature was wanted and the one moment it did
    nothing.
    """
    from .egress_policy import PolicyRefused, from_env
    from .egress_route import RouteUnavailable, open_route
    from .posix_sandbox import backend_for, posix_run
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
        policy = from_env()
    except PolicyRefused as exc:
        shutil.rmtree(work, ignore_errors=True)
        return False, f"[denied] egress policy is unreadable: {exc}"
    route, attempts = None, []
    try:
        if policy is not None:
            backend = backend_for()
            if backend is None:
                raise SandboxUnavailable(_no_backend_reason())
            route = open_route(policy, backend, work)
        outcome = posix_run(cmd, source, work, env=env,
                            timeout_seconds=timeout_seconds,
                            network=policy is None, egress=None if route is
                            None else route.route)
        if outcome is None:
            raise SandboxUnavailable(_no_backend_reason())
        rc, out, plan = outcome
        if route is not None:
            attempts = route.record()["attempts"]
    except RouteUnavailable as exc:
        return False, f"[denied] no egress route for this run: {exc}"
    finally:
        if route is not None:
            route.close()
        shutil.rmtree(work, ignore_errors=True)
    # A run that never started gets no confinement line. The summary states
    # what the kernel enforced, and a failed exec enforced nothing. The probe
    # above catches the common case where the host policy denies the
    # namespace; a backend that starts and then refuses part way through its
    # own setup still reaches here with its summary attached, which is a
    # narrower gap than the one this replaces and is not closed.
    body = _redact(out, bindings)
    lines = (plan.summary(), _egress_line(attempts))
    header = "\n".join(part for part in lines if part)
    out = body if rc == 126 else f"{header}\n{body}".rstrip()
    if rc == 124:
        return False, f"[timeout after {timeout_seconds}s]\n{out}"
    return rc == 0, f"[exit {rc}]\n{out}"


def _no_backend_reason() -> str:
    """Why this host has no sandbox, in words the operator can act on.

    Two hosts reach here and they need different answers. One has neither
    program and wants an install line. The other has the program and a
    kernel that will not let it start, and telling that operator to install
    what they already installed sends them looking in the wrong place.
    """
    from .posix_sandbox import PROGRAM, backend_for
    from .sandbox_probe import REFUSAL_HINT
    backend = backend_for()
    if backend is not None:
        return (f"{PROGRAM[backend]} resolved and its probe run failed, so "
                f"this host cannot confine a command. "
                f"{REFUSAL_HINT.get(backend, '')}").strip()
    return (f"no sandbox backend on this host: install bubblewrap (linux) "
            f"or use macOS sandbox-exec; platform={sys.platform}")


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


def _egress_line(attempts: list) -> str:
    """What the run asked the network for, refusals named.

    The allowed requests are visible in the command's own output anyway. A
    refusal is not: the command sees a connection it could not make and
    usually reports something about its own retry logic instead. So the
    refused hosts are spelled out and the allowed ones are counted.
    """
    if not attempts:
        return ""
    refused = [one for one in attempts if not one["allowed"]]
    carried = len(attempts) - len(refused)
    if not refused:
        return f"[egress: {carried} allowed]"
    named = ", ".join(sorted({f"{one['host']} {one['reason']}"
                              for one in refused}))
    return f"[egress: {carried} allowed, {len(refused)} refused: {named}]"
