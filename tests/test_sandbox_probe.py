"""The probe that separates an installed sandbox from a working one.

Everything here is assertable from any host, because the probe's own runner
is injectable. That is the point: the case it exists to catch is a Linux
kernel setting, and a test that could only run on a host with that setting
would never run.
"""
from harness.sandbox_probe import (PROBE_ARGV, REFUSAL_HINT, forget,
                                   sandbox_starts)


def test_the_probe_asks_for_the_namespaces_the_real_argv_asks_for():
    """A probe that skipped them would pass on the hosts this module catches.

    `--ro-bind / /` needs a mount namespace and `--unshare-pid` needs a pid
    one, and an unprivileged process gets neither without the user namespace
    a restricted host denies. `bwrap --version` would answer on every one of
    those hosts and answer nothing.
    """
    argv = PROBE_ARGV["bwrap"]
    assert argv[:3] == ("--ro-bind", "/", "/")
    assert "--unshare-pid" in argv
    assert argv[-1] == "/bin/true", "the probe runs a command, not a flag"


def test_a_zero_exit_is_startable_and_anything_else_is_not():
    forget()
    assert sandbox_starts("bwrap", "/a/bwrap", run=lambda argv: True)
    forget()
    assert not sandbox_starts("bwrap", "/b/bwrap", run=lambda argv: False)


def test_the_program_under_test_is_the_one_the_probe_runs():
    # A probe that ran the name off PATH rather than the resolved path would
    # answer for a different binary than the one about to confine a command.
    forget()
    seen = []
    sandbox_starts("seatbelt", "/usr/bin/sandbox-exec",
                   run=lambda argv: seen.append(argv) or True)
    assert seen[0][0] == "/usr/bin/sandbox-exec"
    assert seen[0][1:] == list(PROBE_ARGV["seatbelt"])


def test_the_answer_is_cached_per_program_and_not_shared_between_them():
    """One fork per process, not one per command.

    Cached because the kernel setting does not change under a running agent.
    Keyed by program because two paths can resolve to different binaries and
    the second one is the one about to run.
    """
    forget()
    calls = []
    for path in ("/one/bwrap", "/one/bwrap", "/two/bwrap"):
        sandbox_starts("bwrap", path, run=lambda argv: calls.append(argv) or True)
    assert len(calls) == 2
    forget("bwrap", "/one/bwrap")
    sandbox_starts("bwrap", "/one/bwrap", run=lambda argv: calls.append(argv) or True)
    assert len(calls) == 3, "forget() did not drop the answer it was given"


def test_a_backend_with_no_probe_is_reported_startable_rather_than_broken():
    # Refusing an unprobed backend would remove a working sandbox on the
    # strength of a missing table entry, which is a worse failure than the
    # unknown it would be reporting.
    forget()
    assert sandbox_starts("some-future-backend", "/x", run=lambda argv: False)


def test_every_probed_backend_can_say_why_it_refused():
    # The message is the whole value of the probe on the host that fails it.
    # An operator told only that there is no backend goes and installs the
    # program they already have.
    assert set(REFUSAL_HINT) >= set(PROBE_ARGV)
    assert "apparmor_restrict_unprivileged_userns" in REFUSAL_HINT["bwrap"]
