"""endpoints_tools_prose.py -- on a native turn, prose is never a tool call.

When a request carried tool schemas, the provider's tool-call objects are the
only calls. The reply's own words can still hold a line `TOOL name {json}`:
the model may quote one from a file it read, from a tool's output or from a
web page. The session loop parses reply text, so such a line would run with
the model's authority although the model never called anything.

`inert` marks each such line in the prose of a native reply before the
tool-call objects are written out as TOOL lines after it. A marked line is
quoted text to every reader of the reply: the loop, the rescue transforms and
the code that matches results to calls. The marked text is what the session
records, so the ledger shows what the model wrote and that it did not run.

`checked` handles the reply that wrote TOOL lines in prose and made no native
call. Nothing runs. The reply is recorded, the model is told once to use the
function-calling interface, and its next reply stands whatever it holds. At
most one such message is sent for each user request.

A request sent in the text protocol does not come through here. Its TOOL
lines are parsed and run as before.
"""
from __future__ import annotations

import logging

from .local_agent import MalformedBackendOutput

_LOG = logging.getLogger(__name__)

MARK = "> "                              # put before a prose line that reads as a call
NOTICE = "native_tools_notice"           # ledger kind of the one corrective message
CORRECTION = (
    "Nothing ran. Your last reply wrote a tool call as a line of text. In this session "
    "tools are called through the function-calling interface only, and a `TOOL name "
    "{json}` line in a reply's text is not run. If you need a tool, call it through the "
    "interface. Otherwise give your final answer.")


def inert(prose: str) -> "tuple[str, int]":
    """(`prose` with each line that reads as a tool call marked, how many were marked).

    A line reads as a call when the session's parser accepts it, as written
    or after one of the rescue transforms. Lines are cut where the parser
    cuts them, and every other character is kept.
    """
    from .tool_rescue import rescue_tool_calls
    lines, marked = [], 0
    for line in prose.splitlines(keepends=True):
        if rescue_tool_calls(line)[0]:
            line, marked = MARK + line, marked + 1
        lines.append(line)
    text = "".join(lines)
    if rescue_tool_calls(text)[0]:
        raise MalformedBackendOutput(
            "a native reply's text still reads as a tool call after its TOOL lines "
            "were marked; the reply was refused and nothing from it ran")
    return text, marked


def recorded(prose: str) -> str:
    """`prose` as a session's native turn records it, for a stream that showed it unmarked."""
    from . import endpoints_tools
    return inert(prose)[0] if endpoints_tools.current() is not None else prose


def _told(ledger) -> bool:
    """True when this user request already got its one corrective message."""
    for entry in reversed(ledger.entries):
        if entry.kind == NOTICE:
            return True
        if entry.kind == "user":
            return False
    return False


def _emit(session, event: dict) -> None:
    if session.on_event is None:
        return
    try:
        session.on_event(event)
    except Exception:
        _LOG.warning("an event handler failed on %s; the turn goes on",
                     event.get("type"), exc_info=True)


def _sent(box, send, text: str) -> tuple:
    """(reply, prose TOOL lines with no call, record that differs from its calls)."""
    box.stray, box.unfaithful, box.turn = 0, False, None
    resp = send(text)
    stray, wrong = box.stray, box.unfaithful
    box.stray, box.unfaithful = 0, False
    return resp, stray, wrong


def checked(session, send, text: str) -> dict:
    """`send(text)`, plus one corrective exchange when the reply needs it.

    The reply goes back stamped with the native calls it may run (native_turn),
    which is what the loop runs on a native turn.
    """
    box = session.toolbox
    if box is None:
        return send(text)
    from .native_turn import UNFAITHFUL, stamp
    resp, stray, wrong = _sent(box, send, text)
    if not (stray or wrong) or _told(session.ledger):
        return stamp(resp, box)
    written = resp["content"][0]["text"] if resp.get("content") else ""
    session.ledger.append("assistant", written, {
        "backend": resp.get("backend"),
        "receipt": resp.get("x_receipt", {}).get("receipt_id")})
    meta = {"lines": stray, "reason": "call_not_recorded_as_made"} if wrong else {"lines": stray}
    session.ledger.append(NOTICE, UNFAITHFUL if wrong else CORRECTION, meta)
    _LOG.info("a native reply %s; nothing ran and the model was told once",
              "could not be recorded as the calls it made" if wrong
              else f"wrote {stray} TOOL line(s) in its text and made no call")
    _emit(session, {"type": "assistant", "text": written})
    _emit(session, {"type": NOTICE, "lines": stray})
    resp, _stray, _wrong = _sent(box, send, UNFAITHFUL if wrong else CORRECTION)
    return stamp(resp, box)
