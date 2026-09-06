"""posix_sandbox.py -- OS-enforced confinement on the hosts that had none.

`sandboxed_runner` routes a shell command through the Windows low-integrity
namespace, and on every other host it raises `SandboxUnavailable`. That
refusal is honest and it is also the whole reason the fallback policy layer
exists: a Linux or macOS operator's only choices were a refusal or a bare
`subprocess.run(shell=True)` labelled unverifiable. This module gives those
two hosts a third answer.

Two backends, one per platform, both shipped by the OS or a standard package:

  linux   bubblewrap (`bwrap`), an unprivileged user-namespace sandbox
  darwin  Seatbelt (`sandbox-exec`), the macOS policy interpreter

NEITHER CONFINES READS, and the record says so on both. `--ro-bind / /`
remounts the host read-only, which is a write barrier and not a read barrier:
everything on the machine stays legible. The Seatbelt
profile opens with `(allow default)` for the same reason, since a
deny-by-default macOS profile that still lets ordinary build tools run is a
much larger piece of work than this. Confining reads means enumerating what a
toolchain may open, and shipping a flag that said reads were confined while
this argv was running would be worse than shipping no sandbox: it would put a
false guarantee inside a receipt.

What the argv does carry is a denylist. `sandbox_protected_paths` names the
credential directories and files a confined command has no business opening,
and each backend hides them by the only mechanism it has. That is not read
confinement, `READS_CONFINED` still says False on both, and the record counts
the hidden paths under their own name so the two facts cannot be read as one.

What does differ is the process table. bwrap unshares pid, ipc, uts and
cgroup, so a confined process cannot see or signal anything else on the host.
The Seatbelt profile is a filesystem and network policy and leaves the
process table shared. `Confinement` carries both facts, so a receipt reader is
never left to assume the two hosts match.

Network is denied by default on both. A command that needs it says so, and
the record says whether it got it.

Every argv and the profile text are pure functions of their arguments, so
what a Linux host would run is assertable from a Windows one, and the profile
that confines a macOS run can be read in a diff rather than inferred from a
process listing.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from .egress_route import bridge_argv
from .sandbox_confinement import SCHEMA, Confinement
from .sandbox_policy import (ProfileRefused, posix_path, sbpl_profile,
                             seatbelt_argv)
from .sandbox_probe import sandbox_starts
from .sandbox_protected_paths import bwrap_hide_args, present_paths

#: `SCHEMA` and `Confinement` moved next door and are re-exported, because
#: every caller that had them from here still wants them from here and a
#: file split is not a reason to break an import.
__all__ = ["BACKENDS", "PROCESS_ISOLATED", "PROGRAM", "READS_CONFINED",
           "SCHEMA", "Confinement", "ProfileRefused", "backend_for",
           "build", "bwrap_argv", "describe", "posix_run", "routed",
           "sbpl_profile", "seatbelt_argv", "with_egress"]

#: What each platform can enforce, best first. A platform absent from this
#: table has no backend, which is the state every non-Windows host was in.
BACKENDS = {"linux": ("bwrap",), "darwin": ("seatbelt",)}

#: The program each backend needs on PATH.
PROGRAM = {"bwrap": "bwrap", "seatbelt": "sandbox-exec"}

#: Whether a backend confines reads as well as writes. Both are False and the
#: entry stays anyway, because a reader of a receipt has to be told the limit
#: rather than left to infer it from the word sandbox. Flipping a value here
#: without changing the argv would put a false guarantee in every record the
#: backend writes, which is what `test_neither_backend_claims_to_confine_reads`
#: is guarding.
READS_CONFINED = {"bwrap": False, "seatbelt": False}

#: Whether a backend gives the process its own pid, ipc and uts namespaces, so
#: it cannot see or signal the rest of the host. This is the real asymmetry
#: between the two, and it is the one a reader would otherwise guess wrong.
PROCESS_ISOLATED = {"bwrap": True, "seatbelt": False}


def backend_for(platform: str | None = None, which=None) -> str | None:
    """The backend this host can actually use, or None.

    `which` is injectable so the table can be exercised for a platform the
    test is not running on. None means no backend, which is the honest answer
    for a host with neither program installed.
    """
    plat = platform if platform is not None else sys.platform
    look = which if which is not None else shutil.which
    for known, names in BACKENDS.items():
        if plat.startswith(known):
            for name in names:
                if look(PROGRAM[name]):
                    return name
            return None
    return None


def bwrap_argv(program: str, root, work, cmd: str, *,
               network: bool = False, entry: list | tuple = (),
               protected=()) -> list:
    """The bubblewrap command line. Order matters: later binds layer on top.

    `--ro-bind / /` first, then the workspace bound writable over it, then
    the kernel filesystems the shell needs. Read-only is a write barrier and
    nothing more, so the host stays legible to the confined process and
    `READS_CONFINED` says so. `--new-session` is not decoration:
    without it a confined process can push characters into the terminal it
    inherited, which is an escape that does not touch the filesystem.

    `entry` runs inside the namespace and the shell becomes its child. The
    egress bridge is what goes there, because the proxy it forwards to sits
    on the other side of `--unshare-net` and nothing outside the namespace
    can hand a socket across.
    """
    argv = [program, "--die-with-parent", "--new-session",
            "--unshare-pid", "--unshare-ipc", "--unshare-uts", "--unshare-cgroup"]
    if not network:
        argv.append("--unshare-net")
    here, scratch = posix_path(root), posix_path(work)
    argv += ["--ro-bind", "/", "/",
             "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
             "--bind", here, here, "--bind", scratch, scratch]
    # After the workspace bind, so a protected path that happens to sit
    # inside the workspace is hidden rather than exposed by it.
    argv += bwrap_hide_args(protected)
    argv += ["--chdir", here, "--"]
    argv += list(entry)
    argv += ["/bin/sh", "-c", cmd]
    return argv


def routed(egress, network: bool):
    """The route that will actually apply, which is none on an open network.

    A run that already has the network is not being filtered by anything, so
    a record naming host rules would describe a limit no kernel is holding.
    The argv and the record ask the same question here so they cannot answer
    it differently.
    """
    return None if network else egress


def describe(backend: str, root, work, *, network: bool = False,
             egress=None, protected=()) -> Confinement:
    """What a run under `backend` will have enforced when it finishes."""
    route = routed(egress, network)
    return Confinement(
        backend=backend, program=PROGRAM[backend], root=posix_path(root),
        writable=(posix_path(root), posix_path(work)), network=network,
        reads_confined=READS_CONFINED[backend],
        processes_isolated=PROCESS_ISOLATED[backend],
        protected=tuple(protected),
        egress_hosts=() if route is None else tuple(route.hosts),
        egress_port=None if route is None else route.port)


def build(backend: str, program: str, root, work, cmd: str, *,
          network: bool = False, egress=None, protected=()) -> list:
    """The argv for one backend. Pure, so a diff shows what will run.

    The route is passed whole rather than as the piece each backend wants.
    Splitting it into a bridge argv for one and a port number for the other
    would let a caller hand bwrap's half to Seatbelt, and the result would
    be a run with no route under a record that says it has one.
    """
    route = routed(egress, network)
    if backend == "bwrap":
        entry = () if route is None else bridge_argv(route)
        return bwrap_argv(program, root, work, cmd, network=network,
                          entry=entry, protected=protected)
    if backend == "seatbelt":
        profile = sbpl_profile(root, work, network=network,
                               egress_port=None if route is None
                               else route.port, protected=protected)
        return seatbelt_argv(program, profile, cmd)
    raise ProfileRefused(f"no such backend: {backend}")


def posix_run(cmd: str, root, work, *, env: dict, timeout_seconds: int = 120,
              network: bool = False, egress=None, platform: str | None = None,
              which=None, runner=None, probe=None, protected=None) -> tuple:
    """Run `cmd` confined. Returns (returncode, output, Confinement).

    Returns None for the backend rather than raising when the host has none:
    the caller owns that refusal, and it already has a name for it. A host
    whose program is installed and refuses to start returns None for the same
    reason, since `backend_for` reads PATH and PATH does not know whether the
    kernel will allow the namespace. `sandbox_probe` asks it.

    `runner` and `probe` are injectable so the argv can be checked, and the
    refusal reached, without a host that has either program.

    `protected` defaults to the credential denylist under this account's home
    directory, narrowed to the paths that are actually there. Passing an empty
    tuple is how a caller asks for none, and passing a list of (kind, path)
    pairs is how a test asks for a path it just created. The default is read
    here rather than in the builders, which stay pure functions of what they
    are handed.
    """
    backend = backend_for(platform, which)
    if backend is None:
        return None
    found = (which if which is not None else shutil.which)(PROGRAM[backend])
    program = found if isinstance(found, str) else PROGRAM[backend]
    if not (probe if probe is not None else sandbox_starts)(backend, program):
        return None
    hidden = present_paths(Path.home()) if protected is None else protected
    plan = describe(backend, root, work, network=network, egress=egress,
                    protected=hidden)
    argv = build(backend, program, root, work, cmd, network=network,
                 egress=egress, protected=hidden)
    call = runner if runner is not None else _spawn
    rc, out = call(argv, root, with_egress(env, egress), timeout_seconds)
    return rc, out, plan


def with_egress(env: dict, egress) -> dict:
    """The environment plus the proxy variables, or the environment.

    A copy rather than an update in place. The caller's dict is often the
    one a later run will be given, and a proxy address that outlived its
    listener points at a port that answers nothing.
    """
    if egress is None:
        return env
    return {**env, **egress.env()}


def _spawn(argv: list, root, env: dict, timeout_seconds: int) -> tuple:
    try:
        done = subprocess.run(argv, cwd=str(root), env=env, text=True,
                              capture_output=True, timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        return 124, f"[timeout after {timeout_seconds}s]"
    except OSError as exc:
        # The program resolved a moment ago and will not start now. This is a
        # failed run, not an unconfined one, so it may not fall through.
        return 126, f"[sandbox failed to start] {type(exc).__name__}: {exc}"
    return done.returncode, "\n".join(
        part for part in ((done.stdout or "").strip(),
                          (done.stderr or "").strip()) if part)
