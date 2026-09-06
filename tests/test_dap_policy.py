"""The grant boundary a debug adapter runs into, and the record it leaves.

A debug adapter has exactly two ways to reach past the program it is debugging.
`runInTerminal` asks the client to start a process with a command line, a
working directory and an environment the adapter chose. `startDebugging` asks
for a second session against a configuration the adapter supplies. Everything
else it sends is a report about the debuggee.

So these tests are about those two, and about the part that is easy to leave
out: a refusal has to be recorded, not merely returned. The outcome of a refused
run looks the same as the outcome of a run where nothing was ever asked, and the
difference between them is the only thing that makes the record worth reading.
"""
import sys
import time
from pathlib import Path

import pytest

from harness.dap_policy import (EXTERNAL, INTEGRATED, AllowTerminal, DenyAll,
                                OutsideRoot, describe)
from harness.dap_wire import RUN_IN_TERMINAL, START_DEBUGGING

TERMINAL = {"kind": INTEGRATED, "cwd": "", "args": ["python", "app.py", "--v"]}


class Spawned:
    """Stands in for starting a process, and keeps what would have started."""

    def __init__(self) -> None:
        self.calls: list[tuple[list, Path, object]] = []

    def __call__(self, argv, cwd, env) -> int:
        self.calls.append((argv, cwd, env))
        return 4321


def test_deny_all_refuses_both_and_says_which_one_it_refused():
    policy = DenyAll()
    with pytest.raises(PermissionError):
        policy.run_in_terminal(dict(TERMINAL))
    with pytest.raises(PermissionError):
        policy.start_debugging({"request": "launch",
                                "configuration": {"name": "child"}})
    assert [decision.method for decision in policy.decisions] == [
        RUN_IN_TERMINAL, START_DEBUGGING]
    assert all(decision.allowed is False for decision in policy.decisions)


def test_a_refusal_keeps_the_command_line_that_was_asked_for():
    # Redacting it here would answer a question nobody asked. The whole reason
    # to record a refusal is so somebody can read later what the adapter wanted
    # to run on their machine.
    policy = DenyAll()
    with pytest.raises(PermissionError):
        policy.run_in_terminal(dict(TERMINAL))
    assert "app.py" in policy.decisions[0].detail
    assert policy.decisions[0].reason


def test_describe_names_the_terminal_kind_and_the_session():
    assert INTEGRATED in describe(RUN_IN_TERMINAL, dict(TERMINAL))
    assert "child" in describe(START_DEBUGGING,
                               {"request": "attach",
                                "configuration": {"name": "child"}})


def test_describe_survives_arguments_that_carry_nothing_useful():
    # An adapter is free to send a request this side cannot summarize. A
    # describe that raised would turn a refusal into a crash on the answer path.
    assert describe(RUN_IN_TERMINAL, {}) == "integrated terminal in no cwd: no command"
    assert describe(START_DEBUGGING, {}) == "launch session unnamed"
    assert describe("someOtherRequest", {}) == "someOtherRequest"


def test_allow_terminal_starts_the_process_and_hands_back_its_id(tmp_path):
    # A client that answers with an empty body leaves the adapter unable to
    # terminate what it started, so the process outlives the session it was
    # part of. The id is the whole point of allowing at all.
    spawn = Spawned()
    policy = AllowTerminal(tmp_path, spawn=spawn)
    assert policy.run_in_terminal(dict(TERMINAL)) == {"processId": 4321}
    argv, cwd, _ = spawn.calls[0]
    assert argv == ["python", "app.py", "--v"]
    assert cwd == tmp_path.resolve()
    assert policy.decisions[0].allowed is True


def test_an_adapter_that_names_no_directory_gets_the_root_and_not_ours(tmp_path):
    spawn = Spawned()
    AllowTerminal(tmp_path, spawn=spawn).run_in_terminal(
        {"kind": INTEGRATED, "args": ["python"]})
    assert spawn.calls[0][1] == tmp_path.resolve()


def test_a_working_directory_outside_the_root_is_refused(tmp_path):
    spawn = Spawned()
    policy = AllowTerminal(tmp_path / "inside", spawn=spawn)
    (tmp_path / "inside").mkdir()
    with pytest.raises(OutsideRoot):
        policy.run_in_terminal({"kind": INTEGRATED, "cwd": str(tmp_path),
                                "args": ["python"]})
    assert not spawn.calls
    assert policy.decisions[0].allowed is False


def test_a_traversal_back_out_of_the_root_is_resolved_before_it_is_compared(tmp_path):
    # The path is resolved first. A check that compared the string it was given
    # would see a prefix that starts with the root and allow a directory that
    # is nowhere near it.
    root = tmp_path / "inside"
    root.mkdir()
    policy = AllowTerminal(root, spawn=Spawned())
    with pytest.raises(OutsideRoot):
        policy.run_in_terminal({"kind": INTEGRATED,
                                "cwd": str(root / ".." / ".."),
                                "args": ["python"]})


def test_a_symlink_inside_the_root_pointing_out_of_it_is_refused(tmp_path):
    root = tmp_path / "inside"
    root.mkdir()
    (tmp_path / "elsewhere").mkdir()
    try:
        (root / "escape").symlink_to(tmp_path / "elsewhere",
                                     target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this machine does not let the test user make symlinks")
    policy = AllowTerminal(root, spawn=Spawned())
    with pytest.raises(OutsideRoot):
        policy.run_in_terminal({"kind": INTEGRATED,
                                "cwd": str(root / "escape"),
                                "args": ["python"]})


def test_a_cwd_that_is_not_a_path_is_refused_rather_than_coerced(tmp_path):
    policy = AllowTerminal(tmp_path, spawn=Spawned())
    with pytest.raises(OutsideRoot):
        policy.run_in_terminal({"kind": INTEGRATED, "cwd": {"path": "."},
                                "args": ["python"]})


def test_an_external_terminal_is_a_separate_grant(tmp_path):
    # An external window puts the process further out of reach of anything
    # watching, so allowing the integrated kind does not thereby allow it.
    spawn = Spawned()
    policy = AllowTerminal(tmp_path, spawn=spawn)
    with pytest.raises(PermissionError):
        policy.run_in_terminal({"kind": EXTERNAL, "args": ["python"]})
    assert not spawn.calls
    allowed = AllowTerminal(tmp_path, spawn=spawn, allow_external=True)
    assert allowed.run_in_terminal({"kind": EXTERNAL, "args": ["python"]})


def test_an_empty_command_is_refused_before_anything_is_started(tmp_path):
    spawn = Spawned()
    policy = AllowTerminal(tmp_path, spawn=spawn)
    for argv in ([], "python app.py", None):
        with pytest.raises(ValueError):
            policy.run_in_terminal({"kind": INTEGRATED, "args": argv})
    assert not spawn.calls


def test_allow_terminal_still_refuses_a_second_debug_session(tmp_path):
    # A second session is a second adapter with its own reach and no record
    # attached to it. Allowing the narrow case does not widen to this one.
    policy = AllowTerminal(tmp_path, spawn=Spawned())
    with pytest.raises(PermissionError):
        policy.start_debugging({"request": "launch",
                                "configuration": {"type": "python"}})
    assert policy.decisions[-1].allowed is False


def test_the_adapters_environment_is_layered_on_ours_and_a_null_unsets(tmp_path,
                                                                      monkeypatch):
    # Really started, because the null-means-unset rule lives in the spawn and a
    # fake spawn would only be testing that the dict reached it unchanged.
    monkeypatch.setenv("FLYWHEEL_DAP_KEEP", "kept")
    monkeypatch.setenv("FLYWHEEL_DAP_DROP", "dropped")
    written = tmp_path / "env.txt"
    script = ("import os,sys;open(sys.argv[1],'w').write("
              "repr([os.environ.get('FLYWHEEL_DAP_KEEP'),"
              "os.environ.get('FLYWHEEL_DAP_DROP'),"
              "os.environ.get('FLYWHEEL_DAP_ADDED')]))")
    policy = AllowTerminal(tmp_path)
    answer = policy.run_in_terminal(
        {"kind": INTEGRATED, "cwd": str(tmp_path),
         "args": [sys.executable, "-c", script, str(written)],
         "env": {"FLYWHEEL_DAP_DROP": None, "FLYWHEEL_DAP_ADDED": "added"}})
    assert isinstance(answer["processId"], int)
    deadline = time.monotonic() + 30.0
    while not written.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert written.read_text(encoding="utf-8") == repr(["kept", None, "added"])


def test_the_command_runs_without_a_shell_interpreting_it(tmp_path):
    # No shell, so an argument that looks like syntax is an argument. An adapter
    # that sent `&& rm -rf .` as one argv entry gets a program with that name
    # and not a second command.
    written = tmp_path / "argv.txt"
    script = "import sys;open(sys.argv[1],'w').write(repr(sys.argv[2:]))"
    AllowTerminal(tmp_path).run_in_terminal(
        {"kind": INTEGRATED, "cwd": str(tmp_path),
         "args": [sys.executable, "-c", script, str(written), "a && b", "$HOME"]})
    deadline = time.monotonic() + 30.0
    while not written.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert written.read_text(encoding="utf-8") == repr(["a && b", "$HOME"])


def test_a_relative_directory_is_read_against_the_root_and_not_our_own(tmp_path):
    # Adapters send `.` as a matter of course. Resolving it against the
    # directory this client was started in would name a place the adapter never
    # meant, and one the root was never checked against.
    spawn = Spawned()
    (tmp_path / "sub").mkdir()
    AllowTerminal(tmp_path, spawn=spawn).run_in_terminal(
        {"kind": INTEGRATED, "cwd": "sub", "args": ["python"]})
    assert spawn.calls[0][1] == (tmp_path / "sub").resolve()


def test_a_relative_traversal_out_of_the_root_is_still_refused(tmp_path):
    root = tmp_path / "inside"
    root.mkdir()
    spawn = Spawned()
    with pytest.raises(OutsideRoot):
        AllowTerminal(root, spawn=spawn).run_in_terminal(
            {"kind": INTEGRATED, "cwd": "../elsewhere", "args": ["python"]})
    assert not spawn.calls
