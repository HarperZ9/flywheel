"""The session's own bookkeeping, with no adapter behind it.

Everything else about DAP in this repo is tested against a subprocess, because
the wire is where the disagreements between real adapters live. The two facts
here are not about the wire. They are about what a reader sees when it looks at
a session at the wrong moment, and a subprocess cannot be made to land its
events at a chosen moment, so these drive the session directly.

The moment that matters is the end of a run. The protocol defines `exited`,
which carries the code, and `terminated`, which says debugging is over, and it
orders them in neither direction. Real adapters split: debugpy sends `exited`
first, others send `terminated` first. A reader that waits on termination and
then reads the code gets nothing back from half of them.
"""
import threading
import time

from harness.dap_session import DapSession
from harness.dap_witness import summarize


class Peer:
    """Enough of a peer to be handed a handler, and nothing else.

    A session installs itself on its peer in the constructor. Nothing in these
    tests sends, so a peer that only holds the attribute is the whole of it.
    """

    handler = None
    closed = False


def session() -> DapSession:
    return DapSession(Peer(), policy=None)


def test_termination_alone_does_not_carry_the_exit_code():
    # The control for the two tests below. If this ever fails, the ordering
    # they are written against has stopped being reachable and they are
    # proving nothing.
    live = session()
    live.on_event("terminated", {})
    assert live.terminated is True
    assert live.exited is False
    assert live.events.exit_code is None


def test_a_code_that_arrives_after_termination_is_waited_for():
    live = session()
    live.on_event("terminated", {})
    threading.Timer(0.05, live.on_event, ("exited", {"exitCode": 3})).start()
    started = time.monotonic()
    # Reading events.exit_code here returns None: the pair is half written and
    # this is the window a real adapter leaves open.
    assert live.settle_exit(timeout=5.0) == 3
    assert time.monotonic() - started < 5.0


def test_a_fold_taken_at_termination_reports_the_code_and_not_a_blank():
    # The defect this guards is a record, not a race. `terminated: true` beside
    # `exit_code: null` for a program that exited 0 reads as a run whose result
    # was lost, and it would have been written on every adapter that sends
    # termination first.
    live = session()
    live.capabilities = {}
    live.on_event("terminated", {})
    threading.Timer(0.05, live.on_event, ("exited", {"exitCode": 0})).start()
    folded = summarize(live, adapter="none")
    assert folded["terminated"] is True
    assert folded["exit_code"] == 0


def test_a_session_that_ended_without_an_exit_code_says_so_and_moves_on():
    # An attach that detaches ends the session and never reports a code. None
    # is the honest answer and 0 would be a fabricated success. The bound is on
    # the wait, so a reader is not held by an event that is never coming.
    live = session()
    live.on_event("terminated", {})
    started = time.monotonic()
    assert live.settle_exit(timeout=0.1) is None
    assert time.monotonic() - started < 2.0


def test_a_running_program_is_not_waited_on_at_all():
    # Neither end event has arrived, so there is no half-written pair to settle
    # and nothing to wait for. A wait here would put the timeout into the path
    # of every ordinary read of a live session.
    live = session()
    live.on_event("stopped", {"reason": "breakpoint", "threadId": 1})
    started = time.monotonic()
    assert live.settle_exit(timeout=30.0) is None
    assert time.monotonic() - started < 1.0


def test_a_continue_clears_the_stop_it_was_standing_on():
    live = session()
    live.on_event("stopped", {"reason": "breakpoint", "threadId": 1})
    assert live.stop.reason == "breakpoint"
    live.on_event("continued", {"threadId": 1})
    assert live.stop is None
    # And a wait after the resume finds nothing rather than the stale stop.
    assert live.wait_for_stop(timeout=0.05) is None


def test_a_stop_on_a_thread_the_adapter_did_not_name_is_not_invented():
    # Some adapters omit threadId on an exception stop. Coercing the missing
    # field to 0 would name thread zero, which is a real thread id in most
    # runtimes and would attribute the stop to the wrong place.
    live = session()
    live.on_event("stopped", {"reason": "exception", "threadId": "main"})
    assert live.stop.thread_id is None
    assert live.stop.reason == "exception"


def test_an_exit_code_the_adapter_sent_as_a_string_is_refused():
    # `exitCode` is an integer in the specification. A string here becomes None
    # rather than an int() of it: a code that was not sent as a number is a
    # code this side cannot vouch for.
    live = session()
    live.on_event("exited", {"exitCode": "0"})
    assert live.exited is True
    assert live.settle_exit(timeout=0.1) is None
