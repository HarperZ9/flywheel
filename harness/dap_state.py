"""dap_state.py -- what a debug session keeps, apart from what it does.

A debug adapter says most of what it has to say in events rather than in
responses, so a session is two things at once. It is a lifecycle that sends
requests in an order the specification does not fully pin down, and it is a
record of everything that arrived while nothing was asking. This module is the
second one, plus the single declaration the client makes about itself. Nothing
here sends or waits.

Splitting them means the record can be built and read without a wire. A test
that asks what a fold does with a session that ended one way rather than
another constructs the state directly and never starts a subprocess.
"""
from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["Events", "Stop", "client_capabilities", "stop_from"]


@dataclass(frozen=True)
class Stop:
    """One `stopped` event, in the shape a caller asks questions about."""

    reason: str = ""
    thread_id: int | None = None
    description: str = ""
    text: str = ""
    all_threads: bool = False
    hit_breakpoint_ids: tuple = ()


@dataclass
class Events:
    """What the adapter said while nothing was asking.

    Kept whole rather than folded, because the fold belongs to the witness and a
    session that threw away an event it did not recognize would make the record
    a summary of what this client understood rather than of what crossed.
    """

    seen: list[tuple[str, dict]] = field(default_factory=list)
    output: list[dict] = field(default_factory=list)
    exit_code: int | None = None


def client_capabilities(adapter_id: str, *, lines_start_at_one: bool = True,
                        columns_start_at_one: bool = True) -> dict:
    """The initialize arguments, declared rather than guessed.

    `supportsRunInTerminalRequest` and `supportsStartDebuggingRequest` are true
    because this client does answer both, and the answer is a refusal under the
    default policy. Declaring false would be a different statement: it tells the
    adapter not to ask, and then the record shows nothing where a request and a
    refusal belong. The boundary is worth more when it is exercised.

    Line and column bases are declared once here and are the only reason the
    numbers in a stack frame mean anything. An adapter is free to count from
    zero and will, unless it is told.
    """
    return {"clientID": "flywheel", "clientName": "Flywheel",
            "adapterID": str(adapter_id), "locale": "en-US",
            "linesStartAt1": bool(lines_start_at_one),
            "columnsStartAt1": bool(columns_start_at_one),
            "pathFormat": "path",
            "supportsVariableType": True,
            "supportsVariablePaging": False,
            "supportsRunInTerminalRequest": True,
            "supportsStartDebuggingRequest": True,
            "supportsMemoryReferences": False,
            "supportsProgressReporting": False,
            "supportsInvalidatedEvent": False,
            "supportsMemoryEvent": False}


def stop_from(body: dict) -> Stop:
    """Read a `stopped` body, keeping the fields whose type the spec fixes.

    A thread id that is not an integer becomes None rather than a coerced
    number, because a stop attributed to the wrong thread reads as a fact about
    where the program was and is worse than a stop that admits it does not know.
    """
    thread_id = body.get("threadId")
    hits = body.get("hitBreakpointIds")
    return Stop(reason=str(body.get("reason", "")),
                thread_id=thread_id if isinstance(thread_id, int) else None,
                description=str(body.get("description", "")),
                text=str(body.get("text", "")),
                all_threads=bool(body.get("allThreadsStopped")),
                hit_breakpoint_ids=tuple(hits) if isinstance(hits, list) else ())
