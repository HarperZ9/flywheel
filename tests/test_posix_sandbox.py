"""Confinement on the two hosts that used to get a refusal.

The builders are pure, so what a Linux host would run and what a macOS policy
would say are both assertable from a Windows one. That matters more here than
in most places: the alternative is a backend whose argv nobody reads until it
is confining something.
"""
import os
from types import SimpleNamespace

import pytest

from harness.posix_sandbox import (BACKENDS, PROCESS_ISOLATED, PROGRAM,
                                   READS_CONFINED, SCHEMA, Confinement,
                                   ProfileRefused, backend_for, build,
                                   bwrap_argv, describe, posix_run,
                                   sbpl_profile, seatbelt_argv)

def posix_host(monkeypatch, module):
    """Make the module believe it is on a POSIX host.

    The name is read off the module's own `os`, not off the interpreter's.
    Setting `os.name` itself would change which concrete Path class pathlib
    builds, and the test would fail on a detail the code never touches.
    """
    monkeypatch.setattr(
        module, "os", SimpleNamespace(name="posix", environ=os.environ))


def found(*names):
    """A `which` that finds exactly the programs named."""
    return lambda program: f"/usr/bin/{program}" if program in names else None


@pytest.mark.parametrize("platform, present, expected", [
    ("linux", ("bwrap",), "bwrap"),
    ("linux2", ("bwrap",), "bwrap"),
    ("darwin", ("sandbox-exec",), "seatbelt"),
    # The honest null this whole module exists to shrink. A host with the
    # program missing gets no backend rather than a weaker one.
    ("linux", (), None),
    ("darwin", (), None),
    # Windows has its own backend and is not routed here. A table that
    # answered for it would put two sandboxes in front of one command.
    ("win32", ("bwrap", "sandbox-exec"), None),
    ("aix7", ("bwrap",), None),
])
def test_the_backend_table_answers_for_a_host_this_test_is_not_running_on(
        platform, present, expected):
    assert backend_for(platform, found(*present)) == expected


def test_every_backend_named_in_the_table_has_a_program_and_both_verdicts():
    # A backend added to one table and not the others would be selected and
    # then fail on a lookup, or worse, report a guarantee nobody set.
    named = {name for names in BACKENDS.values() for name in names}
    for table in (PROGRAM, READS_CONFINED, PROCESS_ISOLATED):
        assert named == set(table)


def test_bwrap_binds_the_workspace_over_a_read_only_root_in_that_order():
    # The order is the guarantee. `--ro-bind / /` after the workspace bind
    # would remount the workspace read-only and the sandbox would confine
    # nothing while still reporting that it had.
    argv = bwrap_argv("bwrap", "/w", "/tmp/scratch", "make test")
    ro = argv.index("--ro-bind")
    bind = argv.index("--bind")
    assert ro < bind
    assert argv[ro:ro + 3] == ["--ro-bind", "/", "/"]
    assert argv[bind:bind + 3] == ["--bind", "/w", "/w"]
    assert argv[-4:] == ["--chdir", "/w", "--", "/bin/sh"] or \
        argv[-3:] == ["/bin/sh", "-c", "make test"]
    # Without a new session a confined process can push characters into the
    # terminal it inherited, which is an escape the filesystem never sees.
    assert "--new-session" in argv
    assert "--die-with-parent" in argv


@pytest.mark.parametrize("network, present", [(False, True), (True, False)])
def test_the_network_switch_is_the_only_thing_the_flag_moves(network, present):
    argv = bwrap_argv("bwrap", "/w", "/s", "curl example.com",
                      network=network)
    assert ("--unshare-net" in argv) is present
    other = bwrap_argv("bwrap", "/w", "/s", "curl example.com",
                       network=not network)
    assert [a for a in argv if a != "--unshare-net"] == \
        [a for a in other if a != "--unshare-net"]


def test_the_seatbelt_profile_denies_writes_before_it_allows_the_workspace():
    profile = sbpl_profile("/Users/x/repo", "/tmp/scratch")
    deny = profile.index("(deny file-write*)")
    allow = profile.index("(allow file-write*")
    assert deny < allow, "an allow before the deny is overwritten by it"
    assert '(subpath "/Users/x/repo")' in profile
    assert '(subpath "/tmp/scratch")' in profile
    assert "(deny network*)" in profile
    assert "(deny network*)" not in sbpl_profile("/w", "/s", network=True)


def test_neither_backend_claims_to_confine_reads():
    """The flag has to match the argv, and the argv confines writes only.

    `(allow default)` opens the Seatbelt profile and `--ro-bind / /` opens
    the bwrap line. Read-only is a write barrier: under it the whole host,
    `~/.ssh` included, stays readable. A True here would put a guarantee that
    nothing enforces into every receipt these backends write, which is worse
    than the refusal this module replaced.
    """
    assert "(allow default)" in sbpl_profile("/w", "/s")
    argv = bwrap_argv("bwrap", "/w", "/s", "ls")
    at = argv.index("--ro-bind")
    assert argv[at:at + 3] == ["--ro-bind", "/", "/"]
    assert READS_CONFINED == {"bwrap": False, "seatbelt": False}


def test_only_the_backend_with_namespaces_claims_the_process_table():
    # The real asymmetry between the two, and the one a reader would guess
    # wrong. bwrap unshares; the Seatbelt profile is a file and network
    # policy and leaves a confined process able to see every other one.
    argv = bwrap_argv("bwrap", "/w", "/s", "ls")
    assert {"--unshare-pid", "--unshare-ipc", "--unshare-uts"} <= set(argv)
    assert PROCESS_ISOLATED == {"bwrap": True, "seatbelt": False}
    assert "unshare" not in sbpl_profile("/w", "/s")


def test_a_path_that_cannot_be_written_into_a_policy_is_refused():
    # A mis-escaped quote closes the subpath string early and the rest of the
    # line becomes policy nobody wrote. Refusing loses the sandbox; escaping
    # wrong loses the confinement while still reporting one.
    with pytest.raises(ProfileRefused):
        sbpl_profile('/Users/x/re"po', "/tmp/s")
    with pytest.raises(ProfileRefused):
        sbpl_profile("/Users/x/re\npo", "/tmp/s")


def test_seatbelt_passes_the_profile_inline_rather_than_through_a_file():
    # A profile on disk can be rewritten between the write and the exec, and
    # that window is the whole policy.
    profile = sbpl_profile("/w", "/s")
    argv = seatbelt_argv("/usr/bin/sandbox-exec", profile, "ls")
    assert argv[:2] == ["/usr/bin/sandbox-exec", "-p"]
    assert argv[2] == profile
    assert argv[-3:] == ["/bin/sh", "-c", "ls"]
    assert not any(a.endswith(".sb") for a in argv)


def test_the_record_says_which_guarantees_actually_held():
    # Two backends, two different sets of guarantees. A reader who assumed
    # they matched would trust a macOS run further than it earned, so the
    # difference travels with the run, and so does the limit both share.
    linux = describe("bwrap", "/w", "/s")
    mac = describe("seatbelt", "/w", "/s", network=True)
    assert linux.record() == {
        "schema": SCHEMA, "backend": "bwrap", "program": "bwrap",
        "root": "/w", "writable": ["/w", "/s"], "network": False,
        "reads_confined": False, "processes_isolated": True}
    assert mac.record()["processes_isolated"] is False
    assert mac.record()["network"] is True
    assert "network denied" in linux.summary()
    assert "network allowed" in mac.summary()
    # The summary names the limit, not only the guarantee. A reader who is
    # told confined and nothing else supplies the rest from the word.
    assert "reads open" in linux.summary() and "reads open" in mac.summary()
    assert "processes isolated" in linux.summary()
    assert "processes shared" in mac.summary()


def test_build_refuses_a_backend_it_has_no_argv_for():
    assert build("bwrap", "bwrap", "/w", "/s", "ls")[0] == "bwrap"
    assert build("seatbelt", "sb", "/w", "/s", "ls")[0] == "sb"
    with pytest.raises(ProfileRefused):
        build("chroot", "chroot", "/w", "/s", "ls")


def test_a_host_with_no_backend_returns_the_null_rather_than_running_bare():
    # The value the caller turns into SandboxUnavailable. Returning a result
    # here would be a bare subprocess wearing a sandbox's return shape.
    assert posix_run("ls", "/w", "/s", env={}, platform="linux",
                     which=lambda p: None) is None


def test_posix_run_hands_the_built_argv_to_the_runner_it_reports_on():
    # The wiring claim: the argv asserted above is the argv that runs, and
    # the record describes that same run rather than a plan beside it.
    seen = {}

    def runner(argv, root, env, timeout):
        seen["argv"] = argv
        seen["timeout"] = timeout
        return 0, "hello"

    rc, out, plan = posix_run("echo hello", "/w", "/s", env={"PATH": "/bin"},
                              timeout_seconds=7, platform="linux",
                              which=found("bwrap"), runner=runner)
    assert (rc, out) == (0, "hello")
    assert seen["timeout"] == 7
    assert seen["argv"] == bwrap_argv("/usr/bin/bwrap", "/w", "/s",
                                      "echo hello")
    assert plan.backend == "bwrap" and plan.program == "bwrap"


def test_a_sandbox_that_cannot_start_is_a_failure_and_not_a_bare_run(
        tmp_path):
    # The program resolved a moment ago and will not exec now. Falling through
    # would run the command unconfined under a name that says otherwise.
    rc, out, _ = posix_run("echo hi", tmp_path, tmp_path, env={},
                           platform="linux",
                           which=lambda p: str(tmp_path / "no-such-program"))
    assert rc == 126
    assert "failed to start" in out


def test_the_shipped_entry_point_refuses_when_this_host_has_no_backend(
        monkeypatch, tmp_path):
    # Reached through sandboxed_run, not through the module under test. A
    # backend nobody calls would pass every test above and confine nothing.
    from harness import sandboxed_runner
    posix_host(monkeypatch, sandboxed_runner)
    with pytest.raises(sandboxed_runner.SandboxUnavailable) as stop:
        sandboxed_runner.sandboxed_run("echo hi", str(tmp_path))
    assert "no sandbox backend" in str(stop.value)


def test_the_posix_path_labels_its_output_and_redacts_what_it_was_bound(
        monkeypatch, tmp_path):
    # Two claims the Windows path already makes, checked on the new one: a
    # bound value may not come back in the output, and the backend that ran
    # is named where a reader of the transcript will see it.
    from harness import posix_sandbox, sandboxed_runner
    from harness.credential_handles import CredentialBindings
    plan = Confinement(backend="bwrap", program="bwrap", root=str(tmp_path),
                       writable=(str(tmp_path),), network=True,
                       processes_isolated=True)
    posix_host(monkeypatch, sandboxed_runner)
    monkeypatch.setattr(posix_sandbox, "posix_run",
                        lambda *a, **k: (0, "token=s3cret", plan))
    ok, out = sandboxed_runner.sandboxed_run(
        "printenv TOKEN", str(tmp_path),
        bindings=CredentialBindings({"TOKEN": "s3cret"}))
    assert ok
    assert "s3cret" not in out
    assert "[sandbox bwrap:" in out
    # The parity argument made at the call site: the Windows backend cannot
    # restrict the network, so this one does not either by default.
    assert "network allowed" in out


@pytest.mark.skipif(backend_for() is None,
                    reason="this host has no POSIX sandbox backend")
def test_a_real_confined_run_on_this_host(tmp_path):
    # The only test here that proves the policy rather than the string. It
    # runs where a backend exists and skips where none does, which is the
    # same answer the shipped code gives.
    work = tmp_path / "scratch"
    work.mkdir()
    rc, out, plan = posix_run("echo confined > out.txt && cat out.txt",
                              tmp_path, work, env={"PATH": os.environ["PATH"]},
                              network=True)
    assert rc == 0, out
    assert "confined" in out
    assert (tmp_path / "out.txt").read_text().strip() == "confined"
    assert plan.backend == backend_for()


@pytest.mark.skipif(backend_for() is None,
                    reason="this host has no POSIX sandbox backend")
def test_a_real_run_cannot_write_outside_the_workspace(tmp_path):
    # The claim the record makes, tested against the filesystem.
    work, outside = tmp_path / "scratch", tmp_path / "outside"
    work.mkdir()
    outside.mkdir()
    inside = tmp_path / "repo"
    inside.mkdir()
    rc, out, _ = posix_run(f"echo escaped > {outside}/leak.txt",
                           inside, work, env={"PATH": os.environ["PATH"]},
                           network=True)
    assert rc != 0, out
    assert not (outside / "leak.txt").exists()
