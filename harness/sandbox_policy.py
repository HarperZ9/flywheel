"""sandbox_policy.py -- the text a confined run is described in.

Three things live here and they belong together. A path has to be spelled
for the host the run will happen on, which is not the host reading the
function. A path that cannot be spelled has to be refused rather than
approximated. And the macOS backend is text all the way down: its policy is
a string handed to `sandbox-exec`, so the profile and the argv are both
built here.

One speller, used by both backends. `bwrap_argv` binds a path and the
Seatbelt profile names a subpath, and if those two disagreed about how the
workspace is written then the `writable` list in the record would match
neither. Splitting the spelling into each backend would make that drift
possible without making it visible.

Nothing here runs anything. Every function is pure, so what a macOS host
would enforce can be read in a diff from a Windows one.
"""
from __future__ import annotations

from pathlib import PurePosixPath


class ProfileRefused(ValueError):
    """A path cannot be written into a policy without changing its meaning."""


def posix_path(path) -> str:
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
    text = posix_path(path)
    if '"' in text or "\n" in text:
        raise ProfileRefused(f"path cannot be expressed in a policy: {text}")
    return text


#: Character devices a shell needs before it can start at all. Each is a single
#: file or a file descriptor the process already holds, so none of them is a
#: directory a run could leave something behind in.
DEV_WRITES = ('  (literal "/dev/null")',
              '  (literal "/dev/dtracehelper")',
              '  (literal "/dev/tty")',
              '  (regex #"^/dev/fd/[0-9]+$"))')


def sbpl_profile(root, work, *, network: bool = False,
                 egress_port: int | None = None) -> str:
    """The Seatbelt policy confining writes to the workspace.

    Reads stay allowed. That is a real limit of this profile and it is why
    `READS_CONFINED["seatbelt"]` is False.

    The temp directory is not writable and must not become writable here. An
    earlier version allowed `/private/var/folders` so a toolchain would find
    somewhere to put its scratch files, which on macOS is the parent of every
    per-user temp directory the system hands out: a run confined to a
    workspace under that tree could write anywhere else under it, and the
    `writes confined to {root}` line in the record was false for exactly the
    hosts the policy was written for. The caller points `TMPDIR` at the
    scratch directory in `writable` instead, so a toolchain still has one and
    the summary still matches what the kernel enforces.

    `egress_port` opens one hole in the network denial: a TCP connection to
    that port on the loopback interface, where the caller's proxy is
    listening. Seatbelt takes the last matching rule, so the allow has to
    follow the deny to mean anything. Name resolution stays denied, which is
    load-bearing rather than incidental. A confined process that cannot
    resolve has to hand the proxy a name, and the policy the proxy applies is
    written about names.
    """
    writable = [_policy_path(root), _policy_path(work)]
    lines = ["(version 1)", "(allow default)", "(deny file-write*)",
             "(allow file-write*"]
    lines += [f'  (subpath "{path}")' for path in writable]
    lines += list(DEV_WRITES)
    if not network:
        lines.append("(deny network*)")
        if egress_port is not None:
            lines.append(
                f'(allow network-outbound (remote tcp "localhost:'
                f'{_egress_port(egress_port)}"))')
    return "\n".join(lines) + "\n"


def _egress_port(value) -> int:
    """The proxy port, or a refusal.

    A port written into a policy is text the kernel parses, so anything that
    is not a port number is refused here rather than allowed to become a
    profile line whose meaning depends on how `sandbox-exec` reads it.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProfileRefused(f"egress port is not an integer: {value!r}")
    if not 1 <= value <= 65535:
        raise ProfileRefused(f"egress port is outside 1-65535: {value}")
    return value


def seatbelt_argv(program: str, profile: str, cmd: str) -> list:
    """The sandbox-exec command line, profile passed inline.

    Inline rather than through a file: a profile written to disk is a file
    another process on the host can rewrite between the write and the exec,
    and the window is the whole point of the policy.
    """
    return [program, "-p", profile, "/bin/sh", "-c", cmd]
