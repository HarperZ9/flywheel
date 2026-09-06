"""What the two POSIX backends say they will do, read off the builders.

Every builder here is pure, so what a Linux host would run and what a macOS
policy would say are both assertable from a Windows one. That matters more
here than in most places: the alternative is a backend whose argv nobody
reads until it is confining something.

Reading the argv is not watching the kernel obey it. The runs that do that
live in `test_posix_sandbox_entry.py`, next to the entry point that reaches
them.
"""
import pytest

from harness.posix_sandbox import (BACKENDS, PROCESS_ISOLATED, PROGRAM,
                                   READS_CONFINED, SCHEMA, Confinement,
                                   ProfileRefused, backend_for, build,
                                   bwrap_argv, describe, posix_run,
                                   sbpl_profile, seatbelt_argv)


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


def test_the_profile_grants_no_directory_the_record_does_not_name():
    """Every writable subpath is one the summary claims, or a device file.

    This is the shape of the bug it replaces rather than the bug itself. The
    profile used to allow `/private/var/folders`, the parent of every
    per-user temp directory macOS hands out, so a run whose record said
    writes were confined to its workspace could write to any other workspace
    under that tree. Naming the two offenders would let the next widening
    through; asserting the whole set is closed does not.
    """
    profile = sbpl_profile("/Users/x/repo", "/Users/x/scratch")
    granted = {line.split('"')[1] for line in profile.splitlines()
               if line.strip().startswith('(subpath "')}
    assert granted == {"/Users/x/repo", "/Users/x/scratch"}, (
        "the policy allows a directory outside the workspace, so the "
        "`writes confined to {root}` line in the record is not true")
    # The devices stay: a shell that cannot open /dev/null does not start,
    # and none of them is a directory anything can be left behind in.
    assert '(literal "/dev/null")' in profile


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
    # The scratch directory is writable and is not under the workspace, so a
    # line that named the workspace alone would be short by one path.
    assert "writes confined to /w + 1 scratch path," in linux.summary()
    one = Confinement(backend="bwrap", program="bwrap", root="/w",
                      writable=("/w",))
    assert "writes confined to /w," in one.summary()


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
                              which=found("bwrap"), runner=runner,
                              probe=lambda *a: True)
    assert (rc, out) == (0, "hello")
    assert seen["timeout"] == 7
    assert seen["argv"] == bwrap_argv("/usr/bin/bwrap", "/w", "/s",
                                      "echo hello")
    assert plan.backend == "bwrap" and plan.program == "bwrap"


def test_a_sandbox_that_cannot_start_is_a_failure_and_not_a_bare_run(
        tmp_path):
    # The program resolved a moment ago and will not exec now. Falling through
    # would run the command unconfined under a name that says otherwise.
    #
    # The probe is forced past on purpose. It would catch this host first and
    # the run would never be attempted, which is the better outcome and is
    # tested below; this asserts the floor under it, for the exec that fails
    # after a probe has already succeeded.
    rc, out, _ = posix_run("echo hi", tmp_path, tmp_path, env={},
                           platform="linux", probe=lambda *a: True,
                           which=lambda p: str(tmp_path / "no-such-program"))
    assert rc == 126
    assert "failed to start" in out


def test_a_program_that_is_installed_and_refuses_to_start_is_not_a_backend():
    """PATH says installed. The kernel says no. PATH is not the authority.

    Ubuntu 24.04 ships bubblewrap and denies the unprivileged user namespace
    it needs, so `which` finds the program, the table selects it, and every
    run fails with a confinement summary printed over the failure. Returning
    the null here is what turns that into the refusal the caller already
    raises.
    """
    ran = []
    outcome = posix_run("echo hi", "/w", "/s", env={}, platform="linux",
                        which=found("bwrap"), probe=lambda *a: False,
                        runner=lambda *a: ran.append(a) or (0, ""))
    assert outcome is None
    assert ran == [], "a host that cannot confine still ran the command"
