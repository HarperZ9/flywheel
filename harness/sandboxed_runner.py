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

from . import safe_program
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
    scratch_home: bool = False,
    extra_env: "dict[str, str] | None" = None,
    cancel=None, work_hook=None, workspace=None,
) -> tuple[bool, str]:
    """Run `cmd` under this host's sandbox, rooted at `root`.

    `workspace` (workspace_run.Workspace) opens `root` to writes; None changes nothing.

    `cancel` (a threading.Event) stops the command early, exit 130;
    `work_hook(work_dir)` is called before the command starts, so a caller can
    read stdout.txt and stderr.txt there while it runs, on every platform.
    `extra_env` adds plain settings (never credentials; those go through
    `bindings` so they are scrubbed from output) on top of the built
    environment.

    With `scratch_home`, `HOME`, `TEMP` and `TMP` point into the run's own
    scratch directory rather than the caller's (the bench replay, 7.8).

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
        return _posix_sandboxed_run(cmd, root, bindings, timeout_seconds, scratch_home,
                                    extra_env, cancel=cancel, work_hook=work_hook,
                                    workspace=workspace)

    return _windows_sandboxed_run(cmd, root, bindings, timeout_seconds, scratch_home,
                                  extra_env, cancel, work_hook, workspace)


def _windows_sandboxed_run(cmd, root, bindings, timeout_seconds, scratch_home,
                           extra_env, cancel, work_hook, workspace) -> tuple[bool, str]:
    """Run `cmd` in the low-integrity namespace, scratch beside the workspace."""
    source = Path(root).resolve()
    work = Path(tempfile.mkdtemp(prefix="fw_sandbox_", dir=source.parent))
    stdout_path, stderr_path = work / "stdout.txt", work / "stderr.txt"
    done = None     # what work_hook returned: called once the output files are complete
    try:
        env = _build_env(bindings)
        if scratch_home:
            env.update({name: str(work) for name in ("HOME", "TEMP", "TMP")})
        env.update(extra_env or {})
        done = work_hook(work) if work_hook is not None else None
        rc = _execute(source, work, cmd, env, timeout_seconds, stdout_path, stderr_path,
                      cancel, workspace)
        out = _redact(_read_output(stdout_path, stderr_path), bindings)
    finally:
        if callable(done):
            done()
        shutil.rmtree(work, ignore_errors=True)

    if rc == 124:
        return False, f"[timeout after {timeout_seconds}s]\n{out}"
    return rc == 0, f"[exit {rc}]\n{out}"


def _posix_sandboxed_run(
    cmd: str, root: str, bindings: CredentialBindings | None,
    timeout_seconds: int, scratch_home: bool = False,
    extra_env: "dict[str, str] | None" = None, cancel=None, work_hook=None,
    workspace=None,
) -> tuple[bool, str]:
    """Run `cmd` under whichever POSIX backend this host has.

    Scratch goes to the system temp rather than beside the workspace: these
    backends need no sibling, and a folder appearing next to a repo on every
    command buys nothing. It is resolved, because the policy is matched against
    the path the kernel canonicalises to (macOS hands out `/var/folders/...`
    and resolves it to `/private/var/folders/...`). The network and egress
    rules are in `sandbox_route_run`.
    """
    from .sandbox_route_run import routed_run
    source = Path(root).resolve()
    work = Path(tempfile.mkdtemp(prefix="fw_sandbox_")).resolve()
    env = _build_posix_env(bindings, work, scratch_home)
    env.update(extra_env or {})
    streaming, done = None, None
    if cancel is not None or work_hook is not None:
        from .streaming_spawn import make_runner
        streaming = make_runner(work, cancel)
        done = work_hook(work) if work_hook is not None else None
    try:
        outcome = routed_run(cmd, source, work, env, timeout_seconds, streaming, workspace)
    finally:
        if callable(done):
            done()
        shutil.rmtree(work, ignore_errors=True)
    if isinstance(outcome, str):
        return False, outcome
    rc, out, plan, attempts = outcome
    # A run that never started (126) gets no confinement line.
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
                     work: Path, scratch_home: bool = False) -> dict[str, str]:
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
    if scratch_home:
        env["HOME"] = str(work)
    return safe_program.shell_env(env)


def _execute(source: Path, work: Path, cmd: str, env: dict[str, str],
             timeout_seconds: int, stdout_path: Path, stderr_path: Path,
             cancel=None, workspace=None) -> int:
    """Enter the low-integrity namespace and run `cmd` inside it.

    Raises SandboxUnavailable (never the lower-level
    ExecutionInputProtectionUnavailable) when containment cannot be
    established -- an honest null, not a silent fallback.
    """
    from .execution_input_protection import (
        ExecutionInputProtectionUnavailable, protect_execution_namespace,
    )
    comspec = os.environ.get("COMSPEC", "")
    shell = comspec if os.path.isabs(comspec) else safe_program.system_tool("cmd.exe")
    argv = [str(Path(shell).resolve()), "/c", cmd]
    try:
        enter = protect_execution_namespace if workspace is None else workspace.windows_namespace
        with enter(source, work) as runner:
            return runner.run(
                argv, env=env, timeout_seconds=timeout_seconds,
                stdout_path=stdout_path, stderr_path=stderr_path,
                **({"cancel": cancel} if cancel is not None else {}))
    except ExecutionInputProtectionUnavailable as e:
        raise SandboxUnavailable(str(e)) from e


def _build_env(bindings: CredentialBindings | None) -> dict[str, str]:
    active = bindings if bindings is not None else CredentialBindings({})
    return safe_program.shell_env(active.child_environment(os.environ, platform="windows"))


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
