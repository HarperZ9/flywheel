"""sandbox_probe.py -- does this host's sandbox actually start?

`backend_for` answers from the program's presence on PATH, and presence is
not capability. Ubuntu 24.04 ships bubblewrap and also ships
`kernel.apparmor_restrict_unprivileged_userns=1`, which denies the
unprivileged user namespace bwrap needs. On such a host `bwrap` resolves, the
table selects it, every run under it fails at namespace setup, and the
confinement summary printed alongside that failure says the writes were
confined to the workspace. Nothing was confined. Nothing ran.

That is the same defect this row has already been corrected for twice: a
record may state only what the kernel enforced. A program that is installed
and refused is the case a PATH lookup cannot see.

So the smallest command each backend can run is run once, and a host that
fails it has no backend. The caller already knows how to raise that, and an
honest null beats a guarantee attached to a process that never started.

The probe is cached per program for the life of the process. The kernel
setting it detects does not change under a running agent, and paying a fork
per sandboxed command to re-learn the same answer is a cost with nothing
bought by it.
"""
from __future__ import annotations

import subprocess

#: The smallest run that still asks the kernel for what the real argv asks
#: for. `--ro-bind / /` needs a mount namespace and `--unshare-pid` needs a
#: pid one, and an unprivileged process gets neither without the user
#: namespace that a restricted host denies. A probe that skipped them would
#: pass on exactly the hosts this module exists to catch.
PROBE_ARGV = {
    "bwrap": ("--ro-bind", "/", "/", "--unshare-pid", "--", "/bin/true"),
    "seatbelt": ("-p", "(version 1)(allow default)", "/bin/true"),
}

#: Why a backend refused, in the words an operator can act on. Keyed by
#: backend, read by the caller that turns a missing backend into a message.
REFUSAL_HINT = {
    "bwrap": ("bwrap is installed and will not start. On Ubuntu 24.04 and "
              "later this is usually the unprivileged user namespace being "
              "denied: check "
              "`sysctl kernel.apparmor_restrict_unprivileged_userns`."),
    "seatbelt": ("sandbox-exec is installed and will not start. Check that "
                 "the profile interpreter is reachable and not blocked by a "
                 "management profile."),
}

_ANSWERED: dict[tuple, bool] = {}


def sandbox_starts(backend: str, program: str, run=None) -> bool:
    """True when `program` can actually establish `backend`'s confinement.

    A backend with no probe argv is reported startable rather than broken,
    because an unprobed backend is an unknown and refusing one on that basis
    would remove a working sandbox on the strength of a missing table entry.

    `run` is injectable so the outcome can be asserted without a host that
    has either program.
    """
    argv = PROBE_ARGV.get(backend)
    if argv is None:
        return True
    key = (backend, program)
    if key in _ANSWERED:
        return _ANSWERED[key]
    call = run if run is not None else _probe
    _ANSWERED[key] = bool(call([program, *argv]))
    return _ANSWERED[key]


def forget(backend: str | None = None, program: str | None = None) -> None:
    """Drop the cached answer, for a test that changes what the probe sees."""
    if backend is None:
        _ANSWERED.clear()
        return
    _ANSWERED.pop((backend, program), None)


def _probe(argv: list) -> bool:
    try:
        done = subprocess.run(argv, capture_output=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        # Missing, unexecutable, or too slow to answer. Each is a host that
        # cannot be relied on to confine the next command.
        return False
    return done.returncode == 0
