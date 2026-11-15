"""endpoints_tools.py -- native function calling as a wire form of the text protocol.

The coding session records one thing for a tool call, whatever the provider:
the model's reply as text, where each call is a line `TOOL name {json}`. The
loop parses that text, the executor decides and runs each call, and the
results go back as one text message. That is the text protocol, and it is
what the ledger and the receipts are computed over.

Native function calling changes what travels to and from the provider and
nothing else. On the way out, the session's tools are declared as schemas and
earlier native turns are sent back in the provider's own shape. On the way
in, the provider's tool-call objects are written out as TOOL lines after the
reply's prose. From there the loop is the one that always ran. So a call that
arrives natively and the same call written as text produce the same ledger
entries, the same permission prompts and the same results.

On a native turn the tool-call objects are the only calls. A `TOOL name
{json}` line in the reply's own words is marked as quoted text before the
calls are written out, so it never runs (endpoints_tools_prose).

A session turns this on by holding a `Toolbox` and wrapping its model calls
in `active(toolbox)`. A backend called with no toolbox in force behaves as it
did before this module existed.

The text protocol stays the fallback in four cases: the switch is off, the
host is not one whose function calling was checked (see FIRST_PARTY), the
host says the model cannot take tool schemas (learned from its own error,
remembered, and shown once; endpoints_tools_fallback), or an
earlier turn cannot be matched to the native reply it came from (after a
resume or a compaction), in which case that turn travels as text.
"""
from __future__ import annotations

import contextvars
import logging
import re
import threading
import urllib.parse
from contextlib import contextmanager
from dataclasses import dataclass, field

from .local_agent import MalformedBackendOutput

_ACTIVE = contextvars.ContextVar("flywheel_native_tools", default=None)
# Whether the request now being answered on this thread carried the session's tool schemas.
REQUEST_NATIVE = contextvars.ContextVar("flywheel_native_request", default=False)
_LOG = logging.getLogger(__name__)

# Hosts whose function-calling wire format this module was written against.
# Other OpenAI-compatible hosts keep the text protocol unless the switch is
# "on", because a host that accepts `tools` and ignores it would lose calls.
FIRST_PARTY = ("api.openai.com", "api.anthropic.com", "generativelanguage.googleapis.com")
ENV = "FLYWHEEL_NATIVE_TOOLS"            # "0" off, "1" on for every hosted backend
_NO_NATIVE: set = set()                  # (base_url, model) that refused tool schemas
_WORD = re.compile(r"\w+\Z")
KEEP = 256                               # native replies remembered per session

# What a native request says in place of the text protocol's instructions
# (local_tools.TOOLS_SYSTEM). The advice is the same; only the way to call
# changes. Sent on the wire only: the session's own system prompt, and the
# receipt computed over it, keep the text-protocol wording.
GUIDE = ("Tools are available through the function-calling interface. Prefer repo_map then "
         "read_file to locate code, and edit_file (the 'old' text must be unique) over "
         "write_file for changes. After you receive the tool results, continue. When you "
         "have the final answer and need no more tools, reply with the answer and call no "
         "tool. Keep tool use minimal.")
NOTE = ("Call tools through the function-calling interface only. Where these instructions "
        "show a tool as a line `TOOL name {json}`, the line names the tool and its "
        "arguments; do not write TOOL lines yourself.")
# The loop's own message that carries tool results back (harness/local_loop.py).
RESULTS_HEAD = "TOOL RESULTS:\n"
RESULTS_TAIL = ("\n\nContinue if you need more tools, otherwise give the final "
                "answer with no TOOL line.")


class ToolResultClaimed(MalformedBackendOutput):
    """A reply carried a tool result. Only the session produces tool results."""


def mode_from_env(environ) -> str:
    value = (environ.get(ENV) or "").strip()
    return {"0": "off", "1": "on"}.get(value, "auto")


@dataclass
class Reply:
    text: str            # the reply as the session recorded it
    dialect: str
    raw: object          # the assistant content in the provider's own shape
    calls: list          # [{"id", "name", "arguments"}]


@dataclass
class Toolbox:
    """One session's native tool state: what to offer, and what came back."""
    specs: "callable"                      # () -> [{"name", "description", "parameters"}]
    mode: str = "auto"                     # "auto", "on" or "off"
    cache: bool = True                     # provider prompt caching (endpoints_cache)
    replies: list = field(default_factory=list)
    stray: int = 0                         # prose TOOL lines in the last native reply with no call
    turn: "tuple | None" = None            # (record, calls) of the last native reply (native_turn)
    unfaithful: bool = False               # that record did not read back as its calls
    notices: list = field(default_factory=list)   # fallback notices not yet shown
    told: set = field(default_factory=set)        # (base URL, model) this session was told moved
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def remember(self, reply: Reply) -> None:
        with self.lock:
            self.replies.append(reply)
            del self.replies[:-KEEP]

    def snapshot(self) -> list:
        with self.lock:
            return list(self.replies)


@contextmanager
def active(toolbox):
    """While open, hosted backends called on this thread use `toolbox`."""
    token = _ACTIVE.set(toolbox)
    try:
        yield
    finally:
        _ACTIVE.reset(token)


def current():
    return _ACTIVE.get()


def offered(backend) -> "tuple[Toolbox, list] | None":
    """(toolbox, specs) when this backend should speak natively now, else None."""
    box = _ACTIVE.get()
    if box is None or box.mode == "off" or getattr(backend, "tools", None):
        return None
    host = urllib.parse.urlsplit(backend.base_url).hostname or ""
    if box.mode != "on" and host not in FIRST_PARTY:
        return None
    moved = (backend.base_url, backend.model)
    if moved in _NO_NATIVE:             # by this session or another one in the process:
        if moved not in box.told:       # this session says so once, before the reply is used
            from .endpoints_tools_fallback import moved_notice
            box.told.add(moved)
            box.notices.append(moved_notice(backend))
        return None
    specs = box.specs()
    return (box, specs) if specs else None


def refused(backend, status: int, obj, payload: dict) -> bool:
    """True when a host said the model cannot take the tool schemas this module sent.

    Only an error that says tools or function calling are unsupported counts
    (endpoints_tools_fallback); any other 400 is the caller's error to raise.
    The model is remembered, so the caller rebuilds the request and it goes
    out in the text protocol, now and for the rest of the process, and the
    session shows and records one notice. Every other session in the process
    moves with it; each shows and records its own notice at its next request
    for that model (`offered`).
    """
    box = _ACTIVE.get()
    if box is None or status not in (400, 404, 422) or "tools" not in payload:
        return False
    from .endpoints import _error_message
    from .endpoints_tools_fallback import notice, unsupported
    from .provider_fault_boundary import redacted_text
    if not unsupported(obj):
        return False
    _NO_NATIVE.add((backend.base_url, backend.model))
    box.told.add((backend.base_url, backend.model))
    box.notices.append(notice(backend, status))
    _LOG.warning("%s (%s) refused tool schemas with status %s: %s; using the text "
                 "protocol for this model", backend.name, backend.model, status,
                 redacted_text(_error_message(obj).lower()))
    return True


def canonical(prose: str, calls: list) -> str:
    """The reply as the text protocol writes it: prose, then one TOOL line per call.

    Each call is one physical line whatever its arguments hold (native_turn.one_line).
    """
    if not calls:
        return prose
    from .native_turn import one_line
    lines = [f"TOOL {c['name']} {one_line(c['arguments'])}" for c in calls]
    head = prose if not prose or prose.endswith("\n") else prose + "\n"
    return head + "\n".join(lines)


def split_results(message: dict, reply: Reply) -> "list | None":
    """[(ok, output)] for each call of `reply`, read from the loop's results message.

    None when the message is not the results of exactly those calls. The
    outputs are cut at each next call's header. An output that itself holds
    the next header moves the cut, and the text still arrives whole and in
    order across the results.
    """
    from .local_tools import parse_tool_calls
    content = message.get("content") if message.get("role") == "user" else None
    names = [c["name"] for c in reply.calls]
    if not isinstance(content, str) or [n for n, _ in parse_tool_calls(reply.text)] != names:
        return None
    if not (content.startswith(RESULTS_HEAD) and content.endswith(RESULTS_TAIL)):
        return None
    body, out = content[len(RESULTS_HEAD):len(content) - len(RESULTS_TAIL)], []
    for index, name in enumerate(names):
        head = re.match(rf"TOOL {re.escape(name)} -> (ok|FAIL):\n", body)
        if head is None:
            return None
        body = body[head.end():]
        end = len(body)
        if index + 1 < len(names):
            following = re.search(rf"\n\nTOOL {re.escape(names[index + 1])} -> (ok|FAIL):\n", body)
            if following is None:
                return None
            end = following.start()
        out.append((head.group(1) == "ok", body[:end]))
        body = body[end + 2:] if end < len(body) else ""
    return out


def matched(box: Toolbox, dialect: str, messages: list) -> dict:
    """{assistant index: (reply, results)} for turns that can travel natively.

    Remembered replies are matched to assistant messages in order, so two
    turns with the same text keep their own call ids.
    """
    replies, start, found = box.snapshot(), 0, {}
    for index, message in enumerate(messages[:-1]):
        if message.get("role") != "assistant":
            continue
        for at in range(start, len(replies)):
            reply = replies[at]
            if reply.dialect == dialect and reply.text == message.get("content"):
                results = split_results(messages[index + 1], reply)
                if results is not None:
                    found[index] = (reply, results)
                start = at + 1
                break
    return found


def absorb(dialect: str, backend, prose: str, calls: list, raw, claimed: bool,
           native: bool = True) -> str:
    """Check a native reply, remember it, and return its text-protocol form.

    `native` says the request carried tool schemas. Then only `calls` are
    calls: a line of `prose` that reads as one is marked and does not run
    (endpoints_tools_prose), and the record must read back as exactly `calls`
    or nothing runs (native_turn). A text-protocol reply is returned as it came.
    """
    box = _ACTIVE.get()
    if box is None:
        return prose
    if claimed:
        raise ToolResultClaimed(
            f"{backend.name} reply carries a tool result the session did not produce; "
            "the reply was refused and nothing from it ran")
    for call in calls:
        if call.get("arguments_error") or not isinstance(call.get("arguments"), dict):
            raise MalformedBackendOutput(
                f"{backend.name} tool call {call.get('name')!r} has arguments that are "
                "not a JSON object; the call did not run")
        if not _WORD.match(str(call.get("name") or "")):
            raise MalformedBackendOutput(
                f"{backend.name} called a tool whose name the session cannot carry")
    if native:
        from .endpoints_tools_prose import inert
        prose, marked = inert(prose)
        box.stray = 0 if calls else marked
    text = canonical(prose, calls)
    if native:
        from .native_turn import settle
        text = settle(box, text, calls)
    if calls and raw is not None and not box.unfaithful:
        box.remember(Reply(text, dialect, raw, [dict(c) for c in calls]))
    return text
