"""lean_sandbox.py -- resource and write limits for the candidate's one compile.

The candidate's metaprograms run while Lean elaborates it, once, during the
compile that writes the `.olean` every later step judges
(harness/lean_binding.py). Before this module that compile ran with this
user's full rights and only a wall-clock timeout. Here it runs under limits:

Windows (the measuring machine):
- a restricted token (`DISABLE_MAX_PRIVILEGE`) at low integrity, reusing
  harness/windows_low_integrity.py. A low-integrity process cannot write to
  medium-integrity files, which is every file in the user profile and the Lean
  toolchain, so a metaprogram cannot overwrite the toolchain's `.olean` files.
  The build directory is the one place labelled writable;
- a job object with a job-wide memory limit, a job-wide user CPU time limit,
  an active process limit, the basic UI restrictions, and kill-on-close, so no
  process the candidate starts outlives the compile.

Linux: `RLIMIT_AS` and `RLIMIT_CPU` on the compile process. macOS: only
`RLIMIT_CPU`; macOS is not known to enforce `RLIMIT_AS`, so no memory limit is
claimed there (memory_limit_mb is None). No write limit on either.

What this does not stop, on either platform: network access, and reads of any
file this user can read. A metaprogram can still read a secret and send it
out. A no-network sandbox (an AppContainer without the internet capability on
Windows, a network namespace on Linux) is a named follow-up, and until it
lands the receipt says `network: not restricted` and the validation ladder
stops short of `comparator_external`.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

#: Defaults, overridable through the environment. The `import Lean` probes
#: peaked at about 1 GB on the measuring machine (see the record); the memory
#: limit leaves room for Mathlib-sized imports.
DEFAULTS = {"memory_mb": 8192, "cpu_seconds": 300, "active_processes": 4}
_ENV = {"memory_mb": "FLYWHEEL_LEAN_SANDBOX_MEMORY_MB",
        "cpu_seconds": "FLYWHEEL_LEAN_SANDBOX_CPU_SECONDS"}
NOT_STOPPED = ("network access; reads of any file this user can read")
#: The status Windows gave the job's processes when the job-wide CPU time
#: limit was reached (STATUS_QUOTA_EXCEEDED, observed 2026-10-04).
_STATUS_QUOTA_EXCEEDED = 0xC0000044


def limits() -> dict:
    out = dict(DEFAULTS)
    for key, var in _ENV.items():
        raw = os.environ.get(var, "")
        if raw.isdigit() and int(raw) > 0:
            out[key] = int(raw)
    return out


def _info(mechanism: str, lim: dict, **kw) -> dict:
    doc = {"applied": True, "mechanism": mechanism,
           "memory_limit_mb": lim["memory_mb"],
           "cpu_limit_seconds": lim["cpu_seconds"],
           "active_process_limit": lim["active_processes"]
           if os.name == "nt" else None,
           "network": "not restricted", "not_stopped": NOT_STOPPED,
           "peak_memory_mb": None, "cpu_user_seconds": None,
           "limit_hit": None}
    doc.update(kw)
    return doc


def unavailable(detail: str) -> dict:
    return {"applied": False, "mechanism": "none", "detail": detail,
            "network": "not restricted", "not_stopped": NOT_STOPPED}


def run_sandboxed(argv: list, *, writable: Path, cwd: Path, timeout: int,
                  env: "dict | None" = None) -> tuple:
    """Run argv under the limits above: (rc, output, info).

    rc is None when the limits could not be applied; the caller must then
    treat the compile as not run, never run it without them. Output is
    stdout followed by stderr.
    """
    lim = limits()
    if os.name == "nt":
        return _run_windows(argv, writable, cwd, timeout, env, lim)
    return _run_posix(argv, cwd, timeout, env, lim)


def _cap(resource, kind, want: int) -> tuple:
    """(soft, hard) no higher than the hard limit this process already has,
    since an unprivileged process cannot raise it."""
    _, hard = resource.getrlimit(kind)
    if hard != resource.RLIM_INFINITY:
        want = min(want, hard)
    return want, hard if hard != resource.RLIM_INFINITY else want


def _run_posix(argv, cwd, timeout, env, lim) -> tuple:
    import resource
    import sys
    # macOS accepts RLIMIT_AS without enforcing it, so it is not claimed there.
    memory = sys.platform != "darwin"

    def preexec():
        if memory:
            mem = lim["memory_mb"] * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS,
                               _cap(resource, resource.RLIMIT_AS, mem))
        cpu = lim["cpu_seconds"]
        soft, hard = _cap(resource, resource.RLIMIT_CPU, cpu)
        resource.setrlimit(resource.RLIMIT_CPU, (soft, max(soft, hard)))
    from .lean_replay import run_killable
    try:
        rc, out = run_killable(argv, timeout=timeout, env=env, label="lean "
                               "compile (sandboxed)", preexec_fn=preexec,
                               cwd=str(cwd))
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"the sandboxed compile did not start ({exc})", \
            unavailable(str(exc))
    hit = "wall" if rc == 124 else ("cpu" if rc in (-24, -9) else None)
    info = _info("posix-rlimit (" + ("RLIMIT_AS, " if memory else "")
                 + "RLIMIT_CPU)", lim, filesystem="not restricted",
                 limit_hit=hit)
    if not memory:
        info["memory_limit_mb"] = None
    return rc, out, info


def _run_windows(argv, writable, cwd, timeout, env, lim) -> tuple:
    try:
        from . import lean_sandbox_win as win
        from .execution_input_protection import \
            ExecutionInputProtectionUnavailable
    except (ImportError, OSError) as exc:
        return None, f"the Windows sandbox is unavailable ({exc})", \
            unavailable(str(exc))
    out_path, err_path = writable / ".compile.out", writable / ".compile.err"
    try:
        rc, acct = win.run(argv, writable=writable, cwd=cwd, timeout=timeout,
                           env=dict(env if env is not None else os.environ),
                           lim=lim, stdout_path=out_path, stderr_path=err_path)
    except (ExecutionInputProtectionUnavailable, OSError) as exc:
        return None, f"the Windows sandbox could not be applied ({exc})", \
            unavailable(str(exc))
    text = ""
    for p in (out_path, err_path):
        try:
            text += p.read_bytes().decode("utf-8", errors="replace")
            p.unlink()
        except OSError:
            pass
    peak = acct.get("peak_memory_mb")
    hit = None
    if rc == 124:
        hit, text = "wall", text + f"\nlean compile timed out after {timeout}s"
    elif rc == _STATUS_QUOTA_EXCEEDED or (
            rc != 0 and (acct.get("cpu_user_seconds") or 0)
            >= lim["cpu_seconds"]):
        hit = "cpu"
    elif rc != 0 and peak is not None and peak >= lim["memory_mb"] * 0.98:
        hit = "memory"
    if hit in ("cpu", "memory"):
        text += f"\nthe compile reached the sandbox's {hit} limit"
    return rc, text, _info(
        "windows: restricted low-integrity token and a job object "
        "(memory, CPU time, process count, UI limits, kill on close)", lim,
        filesystem="writes limited to the build directory and other "
        "low-integrity locations", peak_memory_mb=peak,
        cpu_user_seconds=acct.get("cpu_user_seconds"), limit_hit=hit)
