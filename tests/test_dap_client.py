"""The client against a real debug adapter subprocess.

The adapter is tests/fake_dap_adapter.py, which frames its own messages by hand
rather than importing harness/dap_wire.py. If it used the same code the client
does, both sides would agree about the wire even when both were wrong, and these
tests would pass on a protocol no real adapter can read.

The lifecycle is the reason this file exists. The specification is read two ways
on when `launch` is answered, and real adapters split along the same line. The
fake takes a flag for each reading, and every lifecycle test here runs against
both, because a client that works against one and deadlocks against the other
looks correct until it is pointed at a different language.
"""
import sys
import time
from pathlib import Path

import pytest

from harness.dap_peer import AdapterError, ConnectionClosed
from harness.dap_policy import AllowTerminal, DenyAll
from harness.dap_client import DapClient

FAKE = [sys.executable, str(Path(__file__).parent / "fake_dap_adapter.py")]

#: Both readings of the lifecycle, run against every test that brings a session
#: up. The empty tuple is an adapter that answers launch straight away.
ORDERINGS = [(), ("--late-launch",)]


def wait_for(predicate, timeout=20.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.01)
    raise AssertionError(f"nothing satisfied {predicate} within {timeout:g}s")


@pytest.fixture
def adapter(tmp_path):
    """Start an adapter, and take it down however the test left it."""
    started = []

    def start(*flags, policy=None, observer=None, program="program.py",
              breakpoints=None, session=True):
        client = DapClient.start(FAKE + list(flags), root=tmp_path,
                                 policy=policy if policy is not None
                                 else DenyAll(), observer=observer)
        started.append(client)
        if session:
            client.start_session("fake", launch={"program": program},
                                 breakpoints=breakpoints, timeout=20.0)
        return client

    yield start
    for client in started:
        client.disconnect(timeout=5.0)
        client.close()


@pytest.mark.parametrize("ordering", ORDERINGS)
def test_a_session_comes_up_under_both_readings_of_the_lifecycle(adapter,
                                                                 ordering):
    # The late ordering is the one that deadlocks a client that waits on the
    # launch response before it configures. Both are legal and both ship.
    client = adapter(*ordering)
    assert client.supports("supportsConfigurationDoneRequest")
    assert client.capabilities["supportsConditionalBreakpoints"] is False
    assert client.wait_for_stop(timeout=20.0).reason == "breakpoint"


@pytest.mark.parametrize("ordering", ORDERINGS)
def test_breakpoints_are_reported_as_the_adapter_placed_them(adapter, ordering):
    # An adapter is allowed to refuse a breakpoint or to move it. A client that
    # reported the request rather than the reply would be reporting breakpoints
    # that are not there and a line the debugger will never stop on.
    client = adapter(*ordering, breakpoints={"program.py": [10, 999, 30]})
    placed = client.session.breakpoints["program.py"]
    assert [entry["verified"] for entry in placed] == [True, False, True]
    assert [entry["line"] for entry in placed] == [10, 999, 31]
    assert placed[1]["message"]


def test_verified_breakpoints_reports_two_numbers_and_not_a_verdict(adapter):
    # An unverified breakpoint is the ordinary case for a file the debuggee has
    # not loaded yet. Folding it to a pass or a fail would put a judgement on
    # the record that the wire did not carry.
    client = adapter(breakpoints={"program.py": [10, 20, 999]})
    assert client.session.verified_breakpoints() == (2, 3)


def test_a_launch_that_fails_reports_its_reason_rather_than_timing_out(adapter):
    # This adapter answers the launch and never sends `initialized`. A client
    # that waited on the event alone would burn its whole timeout and then
    # report a slow adapter, which is the wrong reason.
    started = time.monotonic()
    with pytest.raises(AdapterError) as raised:
        adapter("--launch-fails")
    assert "could not be started" in raised.value.message
    assert time.monotonic() - started < 15.0


def test_configuration_done_is_sent_only_to_an_adapter_that_takes_one(adapter):
    # The fake fails the request if it arrives unadvertised, so a client that
    # sent it unconditionally would raise here instead of in the field, where
    # the error is indistinguishable from the launch having failed.
    client = adapter("--no-config-done")
    assert client.supports("supportsConfigurationDoneRequest") is False
    assert client.session.terminated is False


def test_a_stack_deeper_than_the_read_says_it_was_truncated(adapter):
    client = adapter()
    client.wait_for_stop(timeout=20.0)
    page = client.stack_trace(1, levels=2)
    assert len(page["frames"]) == 2
    assert page["total"] == 5
    assert page["truncated"] is True
    whole = client.stack_trace(1, levels=64)
    assert len(whole["frames"]) == 5
    assert whole["truncated"] is False


def test_a_second_page_of_a_stack_starts_where_the_first_ended(adapter):
    client = adapter()
    client.wait_for_stop(timeout=20.0)
    names = [frame["name"] for frame in
             client.stack_trace(1, start=2, levels=2)["frames"]]
    assert names == ["frame2", "frame3"]


def test_an_expensive_scope_is_not_read(adapter):
    # An adapter marks a scope expensive when reading it costs enough to notice.
    # Paying that for a record nobody asked for is how a debug session becomes
    # the slow part of a run.
    client = adapter()
    client.wait_for_stop(timeout=20.0)
    collected = client.frame_variables(1)
    assert list(collected) == ["Locals"]
    assert [entry["name"] for entry in collected["Locals"]] == ["total", "items"]


def test_a_variables_reference_of_zero_is_not_asked_about(adapter):
    # Zero means the value has no children, by definition rather than by
    # convention. A round trip here would ask an adapter about nothing.
    seen = []
    client = adapter(observer=lambda direction, message: seen.append(
        message.get("command")))
    client.wait_for_stop(timeout=20.0)
    before = seen.count("variables")
    assert client.variables(0) == []
    assert seen.count("variables") == before


def test_evaluate_is_sent_in_a_read_only_context(adapter):
    # `repl` is where adapters expect side effects, down to running debugger
    # commands. The fake echoes the context back, so a client that quietly sent
    # repl is visible here rather than only in a live process it changed.
    client = adapter()
    client.wait_for_stop(timeout=20.0)
    assert client.evaluate("total", frame_id=1)["result"] == "total in watch"


def test_the_client_refuses_the_terminal_the_adapter_asked_for(adapter):
    # Declaring support and then refusing is the point. Declaring no support
    # tells the adapter not to ask, and then the record shows nothing where a
    # request and a refusal belong.
    policy = DenyAll()
    client = adapter("--ask-terminal", policy=policy,
                     breakpoints={"program.py": [10]})
    wait_for(lambda: policy.decisions)
    assert policy.decisions[0].allowed is False
    assert "program.py" in policy.decisions[0].detail
    # The adapter says on its own side of the wire what it was told.
    output = wait_for(lambda: [entry for entry in client.session.events.output
                               if "runInTerminal" in entry.get("output", "")])
    assert "refused" in output[0]["output"]


def test_a_terminal_inside_the_root_is_started_when_the_policy_allows_it(
        adapter, tmp_path):
    starts = []

    def spawn(argv, cwd, env):
        starts.append(argv)
        return 77

    policy = AllowTerminal(tmp_path, spawn=spawn)
    client = adapter("--ask-terminal", policy=policy,
                     breakpoints={"program.py": [10]})
    wait_for(lambda: policy.decisions)
    assert policy.decisions[0].allowed is True
    assert starts == [["python", "program.py"]]
    output = wait_for(lambda: [entry for entry in client.session.events.output
                               if "runInTerminal" in entry.get("output", "")])
    assert "allowed" in output[0]["output"]


def test_a_step_reports_the_stop_it_earned_and_not_the_one_before_it(adapter):
    # The stop is cleared before the request goes out. Clearing after the reply
    # would erase a `stopped` event that arrived first, which is the ordinary
    # case for a step that lands immediately.
    client = adapter()
    assert client.wait_for_stop(timeout=20.0).reason == "breakpoint"
    client.step(1, over=True)
    assert wait_for(lambda: client.session.stop).reason == "step"


def test_continuing_to_the_end_keeps_the_exit_code_and_ends_the_wait(adapter):
    client = adapter()
    client.wait_for_stop(timeout=20.0)
    client.resume(1)
    wait_for(lambda: client.session.terminated)
    # Through settle_exit, not events.exit_code. The fake sends `terminated`
    # before `exited`, as some real adapters do, so the raw field is still None
    # at the moment termination becomes visible.
    assert client.session.settle_exit() == 0
    # A wait for a stop in a program that has already exited returns rather
    # than burning the timeout: the honest answer is that it never stopped.
    started = time.monotonic()
    assert client.wait_for_stop(timeout=20.0) is None
    assert time.monotonic() - started < 5.0


def test_the_events_the_adapter_sent_are_kept_whole(adapter):
    client = adapter()
    client.wait_for_stop(timeout=20.0)
    names = [name for name, _ in client.session.events.seen]
    assert names[0] == "initialized"
    assert "stopped" in names


def test_a_session_is_launched_or_attached_and_not_both(adapter):
    client = adapter(session=False)
    with pytest.raises(ValueError):
        client.start_session("fake", launch={"program": "a.py"},
                             attach={"processId": 1})
    with pytest.raises(ValueError):
        client.start_session("fake")


def test_disconnect_and_close_survive_an_adapter_that_is_already_gone(adapter):
    client = adapter()
    client.wait_for_stop(timeout=20.0)
    client.disconnect(timeout=10.0)
    wait_for(lambda: not client.alive())
    # The exit path is reached from a dead adapter as a matter of course, so
    # neither call raises. A second disconnect is the same situation.
    client.disconnect(timeout=5.0)
    client.close()
    assert client.alive() is False


def test_an_adapter_that_dies_at_startup_leaves_its_reason_readable(adapter):
    # The last thing a dead adapter wrote is usually why it is dead, and a read
    # that races the reader thread finds an empty buffer and reports that the
    # adapter explained nothing.
    client = adapter("--die", session=False)
    with pytest.raises((ConnectionClosed, OSError)):
        client.start_session("fake", launch={"program": "a.py"}, timeout=10.0)
    wait_for(lambda: not client.alive())
    assert "no runtime found" in client.stderr_text()
