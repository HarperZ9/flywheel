"""native_turn.py -- on a native turn the provider's tool-call objects are the calls.

A native reply is recorded as text: its prose, then one line `TOOL name
{json}` for each tool-call object (endpoints_tools.canonical). The session
loop reads calls out of that text, and its parser cuts lines with
`str.splitlines()`, which cuts at more than a newline: \\v, \\f, \\x1c to
\\x1e, U+0085, U+2028 and U+2029 are line ends too. `json.dumps` escapes
every one of those except the last three. An argument holding one of them
used to cut the call's own line, so the model's call was lost and the text
after the cut was read as if the model had written it.

Three things here keep the calls that run equal to the objects the provider
sent:

  one_line     writes a call's arguments with those three characters escaped,
               so the call is one physical line whatever it holds. Other
               text is written as it is, so the record of an argument
               without them is unchanged.
  settle       runs when a native reply is absorbed. The session's own parser
               must read the record back as exactly the native calls (count,
               names, arguments). If it does not, every line that reads as a
               call is marked, nothing runs, and the model is told once.
  turn_calls   is what the loop calls for a reply's calls. A reply stamped as
               native gets the strict parser only, never the rescue step, and
               must equal the stamped objects or the turn is refused. A reply
               with no stamp came in the text protocol and is parsed as
               before, rescue included.

The loop imports this module when it parses a reply. If the import fails the
turn fails before any tool runs.
"""
from __future__ import annotations

import json

from .local_agent import MalformedBackendOutput

KEY = "native_calls"                     # the stamp a session puts on a native reply
_ESCAPES = {"\x85": "\\u0085", "\u2028": "\\u2028", "\u2029": "\\u2029"}
UNFAITHFUL = (
    "Nothing ran. The session could not record your last tool call exactly as you made "
    "it, so it was not run. If you still need the tool, call it again through the "
    "function-calling interface. Otherwise give your final answer.")


def one_line(arguments) -> str:
    """`arguments` as JSON on one physical line, for every reader that cuts lines."""
    text = json.dumps(arguments, ensure_ascii=False)
    for raw, escaped in _ESCAPES.items():
        text = text.replace(raw, escaped)        # raw only inside a JSON string
    if len(text.splitlines()) > 1:               # a line end this table does not know
        text = json.dumps(arguments, ensure_ascii=True)
    return text


def _pairs(calls: list) -> list:
    return [(call["name"], call["arguments"]) for call in calls]


def settle(box, text: str, calls: list) -> str:
    """The record of a native reply, checked against the calls it was written from.

    Sets `box.turn` to (record, calls that may run). When the record does not
    read back as `calls`, the calls that may run are none and `box.unfaithful`
    is set, which the session answers with one corrective message.
    """
    from .local_tools import parse_tool_calls
    if parse_tool_calls(text) == _pairs(calls):
        box.turn = (text, [dict(call) for call in calls])
        return text
    from .endpoints_tools_prose import inert
    text, _marked = inert(text)                  # raises if a line still reads as a call
    box.turn, box.unfaithful = (text, []), True
    return text


def stamp(resp, box):
    """`resp` carrying the native calls of the reply it holds, when that reply was native."""
    turn = getattr(box, "turn", None)
    if turn is not None and isinstance(resp, dict):
        resp[KEY] = {"text": turn[0], "calls": turn[1]}
    return resp


def turn_calls(resp, text: str) -> tuple:
    """(calls, repairs) for the loop: [(name, arguments, preamble)] and the rescue record."""
    from .local_tools import parse_tool_calls
    native = resp.get(KEY) if isinstance(resp, dict) else None
    if native is None:                           # a text-protocol reply, parsed as before
        from .tool_rescue import rescue_tool_calls
        return rescue_tool_calls(text, with_preamble=True)
    found = parse_tool_calls(text, with_preamble=True)
    wanted = _pairs(native["calls"])
    if native["text"] != text or [(name, args) for name, args, _ in found] != wanted:
        raise MalformedBackendOutput(
            "a native reply's record does not read back as the provider's tool calls; "
            "the reply was refused and nothing from it ran")
    return found, []                             # equal to the objects, and no object shared
