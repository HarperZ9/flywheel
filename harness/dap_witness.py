"""dap_witness.py -- keep a recheckable record of a debug session.

The chain machinery is harness/wire_witness.py, shared with the ACP and LSP
witnesses. What is here is the part that is about DAP: the frame context, the
action names, and the fold of a session into the shape a receipt carries.

The frame context has to be overridden rather than inherited. The shared witness
reads `method` and `id` off a message, and a DAP message carries neither. A
record built from the inherited context would show a chain of frames with blank
names, which is a record that a session happened and not a record of what it
did.

Why a debug session is worth witnessing at all: it is the highest-value thing an
agent does that nobody can currently check. A breakpoint hit, a variable read, an
expression evaluated in a live process. Those observations become claims in the
agent's answer, and until now there was no artifact tying the claim to the wire
it came off. This does not make the observation true. It makes it the same
observation later.
"""
from __future__ import annotations

from .action_witness import INPUT, OUTPUT, does_not_prove as action_does_not_prove
from .jsonrpc_peer import SENT
from .wire_witness import WireWitness, transcript_resolver

FRAME_ACTION = "dap/frame"
DECISION_ACTION = "dap/decision"
SESSION_ACTION = "dap/session"
STOP_ACTION = "dap/stop"

WITNESS_SCHEMA = "flywheel.dap-witness/v1"

__all__ = ["DECISION_ACTION", "DapWitness", "FRAME_ACTION", "SESSION_ACTION",
           "STOP_ACTION", "WITNESS_SCHEMA", "does_not_prove", "stop_summary",
           "summarize", "transcript_resolver"]


class DapWitness(WireWitness):
    """Binds one debug adapter connection to one run's action chain."""

    FRAME_ACTION = FRAME_ACTION
    DECISION_ACTION = DECISION_ACTION

    def observe_frame(self, direction: str, message: dict) -> None:
        """The Observer a DAP peer calls for every message in both directions.

        Same chain as the shared version, different context, because a DAP
        message names itself with `command` or `event` and ties itself to
        another message with `seq` and `request_seq`.

        The frame's own number goes on the record as `message_seq`, not `seq`.
        The chain reserves `seq` for a link's position in the log and drops a
        caller's key of that name, so a record built the obvious way carries a
        number that reads like the adapter's and is the log's. It agrees with
        `request_seq` often enough to look right. The shared witness writes
        `message_id` for the same reason.

        `request_seq` is written only where the wire carried one. A request
        with the field present and empty invites a reader to tie it to
        something.
        """
        kind = INPUT if direction == SENT else OUTPUT
        context = {"direction": direction, "type": message.get("type", ""),
                   "command": message.get("command")
                   or message.get("event", ""),
                   "message_seq": message.get("seq"),
                   "outcome": _outcome_of(message)}
        if "request_seq" in message:
            context["request_seq"] = message["request_seq"]
        with self._lock:
            self._witness(message, action=self.FRAME_ACTION, kind=kind,
                          context=context, keep={"direction": direction})
            self.frames += 1

    def record_session(self, session, *, adapter: str = "") -> dict:
        """Witness the folded session beside the frames it was folded from."""
        summary = summarize(session, adapter=adapter)
        witness = self.record(summary, action=SESSION_ACTION, kind=OUTPUT,
                              context={"adapter": adapter,
                                       "terminated": summary["terminated"],
                                       "exit_code": summary["exit_code"]})
        return dict(summary, sha256=witness.sha256, link=witness.link())

    def record_stop(self, stop) -> dict:
        """Witness one place the program stopped, as it stops.

        Taken at the stop rather than at the end, so the order of the stops is
        in the chain. A session folded once at the end could be rewritten to say
        the breakpoints were hit in a different order and nothing would break.
        """
        summary = stop_summary(stop)
        witness = self.record(summary, action=STOP_ACTION, kind=OUTPUT,
                              context={"reason": summary["reason"],
                                       "thread_id": summary["thread_id"]})
        return dict(summary, sha256=witness.sha256, link=witness.link())


def summarize(session, *, adapter: str = "") -> dict:
    """What the session amounted to, in the shape a receipt carries.

    Counts and names, never the values read out of the debuggee. The frame chain
    already binds the frames that carried them, and a variable's value is the
    part of a debug session most likely to be a secret.
    """
    verified, placed = session.verified_breakpoints()
    return {
        "schema": WITNESS_SCHEMA,
        "adapter": adapter,
        "capabilities": sorted(name for name, value
                               in (session.capabilities or {}).items()
                               if value is True),
        "sources_with_breakpoints": len(session.breakpoints),
        "breakpoints_requested": placed,
        "breakpoints_verified": verified,
        "events": len(session.events.seen),
        "event_names": sorted({name for name, _ in session.events.seen}),
        "output_records": len(session.events.output),
        "output_characters": sum(len(str(entry.get("output", "")))
                                 for entry in session.events.output),
        "terminated": session.terminated,
        "exit_code": session.settle_exit(),
        "does_not_prove": does_not_prove(),
    }


def stop_summary(stop) -> dict:
    """One stop, in the shape a receipt carries."""
    return {
        "schema": WITNESS_SCHEMA,
        "reason": stop.reason,
        "thread_id": stop.thread_id,
        "description": stop.description,
        "all_threads": stop.all_threads,
        "hit_breakpoint_ids": list(stop.hit_breakpoint_ids),
    }


def _outcome_of(message: dict) -> str:
    """Whether a response carried an answer or a refusal.

    Requests and events get an empty string. DAP has no success flag on either,
    and inventing one would put a verdict on the record that the wire did not
    carry.
    """
    if message.get("type") != "response":
        return ""
    return "result" if message.get("success") else "error"


def does_not_prove() -> list[str]:
    """What a debug session record leaves open. Never empty."""
    return action_does_not_prove() + [
        "the chain covers frames that crossed this connection, so what the "
        "debuggee did between two stops leaves nothing behind to break a link",
        "a variable's value is what the adapter reported reading, not an "
        "independent observation of the debuggee's memory",
        "a breakpoint marked verified is the adapter's claim that it bound the "
        "location, not evidence that the line was reached",
        "the chain shows the frames were not altered after the session and "
        "says nothing about whether the program under them was correct",
    ]
