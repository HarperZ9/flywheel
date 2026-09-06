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
everything on the machine stays legible, `~/.ssh` included. The Seatbelt
profile opens with `(allow default)` for the same reason, since a
deny-by-default macOS profile that still lets ordinary build tools run is a
much larger piece of work than this. Confining reads means enumerating what a
toolchain may open, and shipping a flag that said reads were confined while
this argv was running would be worse than shipping no sandbox: it would put a
false guarantee inside a receipt.

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
from dataclasses import dataclass
from pathlib import PurePosixPath

SCHEMA = "flywheel.posix-sandbox/v1"

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


class ProfileRefused(ValueError):
    """A path cannot be written into a policy without changing its meaning."""


@dataclass(frozen=True)
class Confinement:
    """Which backend ran, and what it actually enforced."""

    backend: str
    program: str
    root: str
    writable: tuple = ()
    network: bool = False
    reads_confined: bool = False
    processes_isolated: bool = False

    def record(self) -> dict:
        return {"schema": SCHEMA, "backend": self.backend,
                "program": self.program, "root": self.root,
                "writable": list(self.writable), "network": self.network,
                "reads_confined": self.reads_confined,
                "processes_isolated": self.processes_isolated}

    def summary(self) -> str:
        """One line for the transcript, so a difference between hosts shows.

        The limits are named, not only the guarantee. A line that said
        confined and stopped there would let a reader supply the rest from
        the word, and the part they would supply is the part that is false.
        """
        return (f"[sandbox {self.backend}: writes confined to {self.root}, "
                f"reads {'confined' if self.reads_confined else 'open'}, "
                f"processes "
                f"{'isolated' if self.processes_isolated else 'shared'}, "
                f"network {'allowed' if self.network else 'denied'}]")


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


def _posix(path) -> str:
    """The path as the target host spells it.

    These builders describe a run on Linux or macOS, so a path is POSIX text
    whichever host is reading the function. Resolving with the local flavour
    would make the argv depend on the machine asking, and the point of a pure
    builder is that it does not.
    """
    return PurePosixPath(str(path).replace("\\", "/")).as_posix()


def _policy_path(path) -> str:
    """A path safe to write into a Seatbelt profile, or a refusal.

    Escaping is not attempted. A quote in a workspace path is rare and a
    mis-escaped one silently widens the policy, so this refuses and the
    caller falls back to no sandbox rather than to a weaker one nobody was
    told about.
    """
    text = _posix(path)
    if '"' in text or "\n" in text:
        raise ProfileRefused(f"path cannot be expressed in a policy: {text}")
    return text


def sbpl_profile(root, work, *, network: bool = False) -> str:
    """The Seatbelt policy confining writes to the workspace.

    Reads stay allowed. That is a real limit of this profile and it is why
    `READS_CONFINED["seatbelt"]` is False.
    """
    writable = [_policy_path(root), _policy_path(work)]
    lines = ["(version 1)", "(allow default)", "(deny file-write*)",
             "(allow file-write*"]
    lines += [f'  (subpath "{path}")' for path in writable]
    # A process that cannot write these cannot start most toolchains, and
    # neither is a way out of the workspace.
    lines += ['  (subpath "/private/tmp")',
              '  (subpath "/private/var/folders")',
              '  (literal "/dev/null")',
              '  (literal "/dev/dtracehelper")',
              '  (literal "/dev/tty")',
              '  (regex #"^/dev/fd/[0-9]+$"))']
    if not network:
        lines.append("(deny network*)")
    return "\n".join(lines) + "\n"


def bwrap_argv(program: str, root, work, cmd: str, *,
               network: bool = False) -> list:
    """The bubblewrap command line. Order matters: later binds layer on top.

    `--ro-bind / /` first, then the workspace bound writable over it, then
    the kernel filesystems the shell needs. Read-only is a write barrier and
    nothing more, so the host stays legible to the confined process and
    `READS_CONFINED` says so. `--new-session` is not decoration:
    without it a confined process can push characters into the terminal it
    inherited, which is an escape that does not touch the filesystem.
    """
    argv = [program, "--die-with-parent", "--new-session",
            "--unshare-pid", "--unshare-ipc", "--unshare-uts", "--unshare-cgroup"]
    if not network:
        argv.append("--unshare-net")
    here, scratch = _posix(root), _posix(work)
    argv += ["--ro-bind", "/", "/",
             "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
             "--bind", here, here, "--bind", scratch, scratch,
             "--chdir", here,
             "--", "/bin/sh", "-c", cmd]
    return argv


def seatbelt_argv(program: str, profile: str, cmd: str) -> list:
    """The sandbox-exec command line, profile passed inline.

    Inline rather than through a file: a profile written to disk is a file
    another process on the host can rewrite between the write and the exec,
    and the window is the whole point of the policy.
    """
    return [program, "-p", profile, "/bin/sh", "-c", cmd]


def describe(backend: str, root, work, *, network: bool = False) -> Confinement:
    """What a run under `backend` will have enforced when it finishes."""
    return Confinement(
        backend=backend, program=PROGRAM[backend], root=_posix(root),
        writable=(_posix(root), _posix(work)), network=network,
        reads_confined=READS_CONFINED[backend],
        processes_isolated=PROCESS_ISOLATED[backend])


def build(backend: str, program: str, root, work, cmd: str, *,
          network: bool = False) -> list:
    """The argv for one backend. Pure, so a diff shows what will run."""
    if backend == "bwrap":
        return bwrap_argv(program, root, work, cmd, network=network)
    if backend == "seatbelt":
        return seatbelt_argv(
            program, sbpl_profile(root, work, network=network), cmd)
    raise ProfileRefused(f"no such backend: {backend}")


def posix_run(cmd: str, root, work, *, env: dict, timeout_seconds: int = 120,
              network: bool = False, platform: str | None = None,
              which=None, runner=None) -> tuple:
    """Run `cmd` confined. Returns (returncode, output, Confinement).

    Returns None for the backend rather than raising when the host has none:
    the caller owns that refusal, and it already has a name for it.
    `runner` is injectable so the argv can be checked without a sandbox.
    """
    backend = backend_for(platform, which)
    if backend is None:
        return None
    found = (which if which is not None else shutil.which)(PROGRAM[backend])
    program = found if isinstance(found, str) else PROGRAM[backend]
    plan = describe(backend, root, work, network=network)
    argv = build(backend, program, root, work, cmd, network=network)
    call = runner if runner is not None else _spawn
    rc, out = call(argv, root, env, timeout_seconds)
    return rc, out, plan


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
