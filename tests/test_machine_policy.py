"""The settings an administrator pins, and the three ways a file can fail.

The engine reads its security answers from the environment, which whoever
starts the process controls. On a shared machine that is the wrong place for a
standing "no", so a file at an administrator-owned path outranks it. Everything
here is about the ways that arrangement can be turned back into a "yes".

The ownership rule is the load-bearing part and it is tested twice: once as a
pure function over stat fields, which runs on any host, and once against the
platform's own answer, which only proves the plumbing works. Neither test needs
an administrator, because a test that only runs for root is a test that does not
run.
"""
import json
import os

import pytest

from harness.machine_policy import PINNABLE, Policy, load_policy, policy_path
from harness.machine_policy_owner import ADMIN_SIDS, insecure_reason
from harness.tool_sandbox_bridge import fallback_from_env

TRUSTED = {"owner": lambda path: None}
ALLOW = {"FLYWHEEL_ALLOW_UNSANDBOXED": "1"}


class Stat:
    """The two stat fields the POSIX rule reads, and nothing else."""

    def __init__(self, uid, mode):
        self.st_uid = uid
        self.st_mode = mode


def write(tmp_path, document):
    path = tmp_path / "policy.json"
    path.write_text(document if isinstance(document, str)
                    else json.dumps(document), encoding="utf-8")
    return path


def test_a_host_nobody_configured_leaves_the_decision_where_it_was(tmp_path):
    # Absence is the ordinary case. A policy layer that treated it as a failure
    # would refuse on every machine that never had an administrator.
    absent = load_policy(tmp_path / "policy.json", **TRUSTED)
    assert absent.pins == {}
    assert absent.problem is None
    assert fallback_from_env(ALLOW, absent) == "disclose"


def test_a_file_anyone_could_have_written_is_ignored_and_says_so(tmp_path):
    # The whole point of the layer. A pin obeyed without checking who wrote it
    # hands the pin to whoever wrote it, and the permissive direction is the
    # one an attacker wants.
    path = write(tmp_path, {"allow_unsandboxed": True})
    result = load_policy(path, owner=lambda p: "owned by uid 1000, not root")
    assert result.pins == {}
    assert "uid 1000" in result.problem
    assert fallback_from_env({}, result) == "refuse"


def test_a_policy_that_cannot_be_read_pins_every_setting_closed(tmp_path):
    # Not the same as no policy. An administrator's file that is present and
    # broken means somebody meant to constrain this host, so the environment
    # does not get to answer instead.
    path = write(tmp_path, "{not json")
    result = load_policy(path, **TRUSTED)
    assert result.pins == PINNABLE
    assert "pinned closed" in result.problem
    assert fallback_from_env(ALLOW, result) == "refuse"


@pytest.mark.parametrize("document, reason", [
    ({"allow_unsandbox": False}, "unknown key"),
    ({"allow_unsandboxed": "yes"}, "expected bool"),
    ({"allow_unsandboxed": 1}, "expected bool"),
    ([{"allow_unsandboxed": False}], "not an object"),
])
def test_a_misspelled_policy_is_a_broken_policy(tmp_path, document, reason):
    # `allow_unsandbox: false` is how the setting gets misspelled, and the
    # misspelled half is the half that was meant to say no. Reading it as an
    # empty policy would make the typo weaker than writing nothing at all.
    result = load_policy(write(tmp_path, document), **TRUSTED)
    assert result.pins == PINNABLE
    assert reason in result.problem
    assert fallback_from_env(ALLOW, result) == "refuse"


def test_a_pin_outranks_the_environment_in_both_directions(tmp_path):
    # Refusing harder than the environment asked is the case that matters, and
    # the other direction is checked with it: a pin that could only tighten
    # would be a second name for the shipped default.
    closed = load_policy(write(tmp_path, {"allow_unsandboxed": False}),
                         **TRUSTED)
    assert closed.problem is None
    assert fallback_from_env(ALLOW, closed) == "refuse"
    open_ = load_policy(write(tmp_path, {"allow_unsandboxed": True}), **TRUSTED)
    assert fallback_from_env({}, open_) == "disclose"


def test_the_directory_is_checked_and_not_only_the_file(tmp_path):
    # A file nobody else can write is still replaceable by anyone who can write
    # the directory holding it, so a check that stopped at the file would pass
    # a policy an attacker can swap out between reads.
    path = write(tmp_path, {"allow_unsandboxed": True})
    seen = []

    def owner(candidate):
        seen.append(candidate.name)
        return "world-writable" if candidate == tmp_path else None

    result = load_policy(path, owner=owner)
    assert seen == ["policy.json", tmp_path.name]
    assert result.pins == {}
    assert "world-writable" in result.problem


@pytest.mark.parametrize("uid, mode, reason", [
    (1000, 0o644, "not root"),
    (0, 0o646, "world-writable"),
    (0, 0o664, "group-writable"),
    (0, 0o644, None),
    (0, 0o600, None),
])
def test_the_posix_rule_reads_owner_and_reach(uid, mode, reason):
    problem = insecure_reason(Stat(uid, mode), posix=True)
    assert (reason in problem) if reason else (problem is None)


def test_a_windows_stat_is_not_read_as_though_it_were_a_posix_one():
    # Why the platform is a parameter. Windows fills st_uid with 0 and st_mode
    # with something that has no group bits, so the POSIX rule applied to a
    # Windows stat reports a root-owned file with no reach and passes every
    # file on the disk.
    problem = insecure_reason(Stat(0, 0o644), posix=False)
    assert "not readable from a stat" in problem


@pytest.mark.skipif(os.name != "nt", reason="the security API is Windows only")
def test_the_windows_owner_lookup_answers_and_fails_closed(tmp_path):
    # This proves the ctypes plumbing, not the verdict: whether an ordinary
    # file passes depends on whether the run is elevated, and asserting either
    # way would make the test report the session rather than the code.
    from harness.machine_policy_owner import windows_owner_problem
    path = write(tmp_path, {"allow_unsandboxed": False})
    verdict = windows_owner_problem(path)
    assert verdict is None or verdict.startswith("owned by S-1-")
    missing = windows_owner_problem(tmp_path / "no-such-file.json")
    assert missing and "lookup failed" in missing
    assert "S-1-5-32-544" in ADMIN_SIDS


@pytest.mark.parametrize("platform, expected", [
    ("darwin", "/Library/Application Support/flywheel/policy.json"),
    ("linux", "/etc/flywheel/policy.json"),
])
def test_the_path_is_one_that_already_needs_elevation(platform, expected):
    # The path carries the authority. A policy read from somewhere a user can
    # write would check ownership and find the user, every time.
    assert policy_path(platform, {}).as_posix().endswith(expected)
    windows = policy_path("win32", {"ProgramData": r"C:\ProgramData"})
    assert windows.as_posix() == "C:/ProgramData/flywheel/policy.json"
    # The answer is for the platform named, not for the host asking. A Linux
    # run reading the Windows answer used to get one filename with backslashes
    # in it, which reads as a path and compares as a name.
    assert windows.parts[-3:] == ("ProgramData", "flywheel", "policy.json")


def test_the_refusal_names_the_pin_rather_than_a_variable_that_is_outranked(
        tmp_path, monkeypatch):
    # An operator who already exported the variable reads the generic advice as
    # the engine ignoring them. A refusal that names a way out which cannot work
    # on this host is worse than no advice, because it costs a round of trying.
    from harness import machine_policy, sandboxed_runner
    from harness.tool_sandbox_bridge import make_sandboxed_runner

    def no_sandbox(*a, **k):
        raise sandboxed_runner.SandboxUnavailable("no sandbox on this host")

    monkeypatch.setattr(sandboxed_runner, "sandboxed_run", no_sandbox)
    pinned = machine_policy.Policy(pins={"allow_unsandboxed": False},
                                   path=str(tmp_path / "policy.json"))
    monkeypatch.setattr(machine_policy, "load_policy", lambda *a, **k: pinned)
    ok, out = make_sandboxed_runner(bindings=None)("echo open", str(tmp_path))
    assert not ok
    assert "policy.json" in out
    assert "does not override it" in out
    # The control. With nothing pinned the advice is the ordinary one, so the
    # test above is reading the pin rather than a string that is always there.
    monkeypatch.setattr(machine_policy, "load_policy",
                        lambda *a, **k: machine_policy.Policy())
    _, plain = make_sandboxed_runner(bindings=None)("echo open", str(tmp_path))
    assert "policy.json" not in plain
    assert "FLYWHEEL_ALLOW_UNSANDBOXED=1" in plain


def test_an_empty_policy_pins_nothing_by_name():
    # `pinned` returning None is what the callers branch on, and None has to
    # mean unpinned rather than pinned-false for a boolean setting.
    assert Policy().pinned("allow_unsandboxed") is None
    assert Policy(pins={"allow_unsandboxed": False}).pinned(
        "allow_unsandboxed") is False
