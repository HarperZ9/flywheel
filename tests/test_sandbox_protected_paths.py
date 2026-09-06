"""The credential denylist, and the claim it is careful not to make.

Every assertion here is a pure function of its arguments, so what a Linux
host would run and what a macOS profile would say are both readable from a
Windows checkout. The real-run half lives in `test_posix_sandbox_entry.py`,
next to the entry point that reaches a kernel.
"""
import pytest

from harness.posix_sandbox import (ProfileRefused, bwrap_argv, describe,
                                   posix_run, sbpl_profile)
from harness.sandbox_protected_paths import (CREDENTIAL_DIRECTORIES,
                                             CREDENTIAL_FILES, default_paths,
                                             present_paths)


def found(name):
    return lambda program: f"/usr/bin/{program}" if program == name else None


def test_the_default_set_is_absolute_under_the_home_it_was_given():
    # Relative names would be resolved by the confined process against its
    # own working directory, which is the workspace, so the rule would hide
    # a path nobody was worried about and leave the real one open.
    paths = default_paths("/home/a")
    assert ("dir", "/home/a/.ssh") in paths
    assert ("file", "/home/a/.netrc") in paths
    assert all(path.startswith("/home/a/") for _, path in paths)
    assert len(paths) == len(CREDENTIAL_DIRECTORIES) + len(CREDENTIAL_FILES)


def test_a_windows_home_is_written_the_way_the_target_host_spells_it():
    # The builders describe a POSIX run whichever host is asking. A backslash
    # reaching a profile or an argv would be a literal character in a path
    # name, not a separator.
    paths = default_paths("C:\\Users\\a")
    assert ("dir", "C:/Users/a/.ssh") in paths


def test_the_set_covers_the_credentials_worth_stealing():
    # Not an inventory for its own sake. Each of these is a working identity
    # a confined command could spend, and the list is the whole value of the
    # feature: what is not named here stays readable.
    names = set(CREDENTIAL_DIRECTORIES) | set(CREDENTIAL_FILES)
    for expected in (".ssh", ".aws", ".gnupg", ".config/gh",
                     ".flywheel/keys", ".netrc", ".git-credentials"):
        assert expected in names, f"{expected} is readable under the sandbox"


def test_bwrap_hides_a_directory_and_a_file_by_their_two_mechanisms():
    # bubblewrap has no read barrier, only a mount. A directory takes an
    # empty tmpfs and a single file takes /dev/null, because a character
    # device cannot be mounted over a directory.
    argv = bwrap_argv("/usr/bin/bwrap", "/w", "/s", "true",
                      protected=(("dir", "/h/.ssh"), ("file", "/h/.netrc")))
    assert argv[argv.index("--tmpfs", argv.index("--bind")) + 1] == "/h/.ssh"
    hide = argv.index("/h/.netrc")
    assert argv[hide - 2:hide] == ["--ro-bind", "/dev/null"]


def test_the_hide_mounts_layer_over_the_workspace_and_not_under_it():
    # A workspace that contains a protected path must not re-expose it. bwrap
    # applies binds in order, so the later one wins and these have to be
    # later than the workspace bind.
    argv = bwrap_argv("/usr/bin/bwrap", "/h", "/s", "true",
                      protected=(("dir", "/h/.ssh"),))
    assert argv.index("/h/.ssh") > max(
        i for i, part in enumerate(argv) if part == "--bind")
    assert argv.index("/h/.ssh") < argv.index("--chdir")


def test_the_profile_denies_read_data_after_allow_default():
    # SBPL takes the last matching rule for an operation. A deny placed
    # before `(allow default)` would be overridden by it and the profile
    # would read as protective while protecting nothing.
    text = sbpl_profile("/w", "/s",
                        protected=(("dir", "/h/.ssh"), ("file", "/h/.netrc")))
    lines = text.splitlines()
    assert lines.index("(deny file-read-data") > lines.index("(allow default)")
    assert '  (subpath "/h/.ssh")' in lines
    assert lines[-1] == '  (literal "/h/.netrc"))'


def test_metadata_reads_are_left_alone_on_purpose():
    # `file-read*` would deny the stat as well, which breaks `ls ~` for a
    # gain of nothing: these path names are public knowledge. The claim is
    # that the contents cannot be read.
    text = sbpl_profile("/w", "/s", protected=(("dir", "/h/.ssh"),))
    assert "(deny file-read*" not in text
    assert "(deny file-read-data" in text


def test_a_protected_path_that_cannot_be_expressed_refuses():
    # Same rule as every other path in this profile. A mis-escaped quote
    # silently widens a policy, and a refusal the caller turns into no
    # sandbox is better than a sandbox that is quietly weaker.
    with pytest.raises(ProfileRefused):
        sbpl_profile("/w", "/s", protected=(("dir", '/h/a"b'),))


def test_no_protected_paths_leaves_the_profile_and_the_argv_untouched():
    # The feature is additive. A caller that asks for none gets exactly what
    # the previous version produced, so the denylist cannot be blamed for a
    # behaviour change on a host that did not opt in.
    assert sbpl_profile("/w", "/s") == sbpl_profile("/w", "/s", protected=())
    assert bwrap_argv("/usr/bin/bwrap", "/w", "/s", "true") == bwrap_argv(
        "/usr/bin/bwrap", "/w", "/s", "true", protected=())


def test_the_record_counts_hidden_paths_and_still_says_reads_are_open():
    # The false-success control for this whole feature. A denylist over an
    # open filesystem is not read confinement, and the summary has to carry
    # both facts in one line or a reader will take the first for the second.
    plan = describe("bwrap", "/w", "/s",
                    protected=(("dir", "/h/.ssh"), ("file", "/h/.netrc")))
    assert plan.reads_confined is False
    assert "reads open" in plan.summary()
    assert "2 paths hidden" in plan.summary()
    assert plan.record()["protected"] == ["/h/.ssh", "/h/.netrc"]
    assert "1 path hidden" in describe(
        "bwrap", "/w", "/s", protected=(("dir", "/h/.ssh"),)).summary()


def test_the_filter_keeps_what_is_there_and_drops_what_is_not():
    # A hide is a mount, and on Linux the mount point has to be created on a
    # read-only bind. Hiding a path the host does not have is a mount that
    # can fail and take the run with it, for a protection worth nothing.
    everything = present_paths("/h", exists=lambda path: True)
    assert everything == default_paths("/h")
    assert present_paths("/h", exists=lambda path: False) == ()
    only_ssh = present_paths("/h", exists=lambda path: path.endswith("/.ssh"))
    assert only_ssh == (("dir", "/h/.ssh"),)


def test_a_run_that_asks_for_nothing_still_hides_what_this_account_has():
    # The default is the point. A caller who never heard of this module gets
    # the protection, and a caller who wants none has to say so.
    #
    # The set is whatever this host actually has, which on a bare runner can
    # be empty, so the assertion is that the record and the argv agree and
    # that nothing outside the table was hidden. `present_paths` above
    # covers what the set contains.
    seen = {}
    _, _, plan = posix_run("true", "/w", "/s", env={}, platform="linux",
                           which=found("bwrap"), probe=lambda *a: True,
                           runner=lambda argv, *a: (seen.update(argv=argv),
                                                    (0, ""))[1])
    hidden = plan.record()["protected"]
    named = set(CREDENTIAL_DIRECTORIES) | set(CREDENTIAL_FILES)
    assert all(path in seen["argv"] for path in hidden), (
        "the record names a path the argv never hid")
    assert all(any(path.endswith("/" + name) for name in named)
               for path in hidden), "a path outside the table was hidden"
