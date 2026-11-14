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

A session turns this on by holding a `Toolbox` and wrapping its model calls
in `active(toolbox)`. A backend called with no toolbox in force behaves as it
did before this module existed.

The text protocol stays the fallback in four cases: the switch is off, the
host is not one whose function calling was checked (see FIRST_PARTY), the
host refuses tool schemas (learned from its own error and remembered), or an
earlier turn cannot be matched to the native reply it came from (after a
resume or a compaction), in which case that turn travels as text.
"""
from __future__ import annotations

import contextvars
import json
import logging
import re
import threading
import urllib.parse
from contextlib import contextmanager
from dataclasses import dataclass, field

from .local_agent import MalformedBackendOutput

_ACTIVE = contextvars.ContextVar("flywheel_native_tools", default=None)
_LOG = logging.getLogger(__name__)

# Hosts whose function-calling wire format this module was written against.
# Other OpenAI-compatible hosts keep the text protocol unless the switch is
# "on", because a host that accepts `tools` and ignores it would lose calls.
FIRST_PARTY = ("api.openai.com", "api.anthropic.com", "generativelanguage.googleapis.com")
ENV = "FLYWHEEL_NATIVE_TOOLS"            # "0" off, "1" on for every hosted backend
_NO_NATIVE: set = set()                  # (base_url, model) that refused tool schemas
_WORD = re.compile(r"^\w+$")
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
    if (backend.base_url, backend.model) in _NO_NATIVE:
        return None
    host = urllib.parse.urlsplit(backend.base_url).hostname or ""
    if box.mode != "on" and host not in FIRST_PARTY:
        return None
    specs = box.specs()
    return (box, specs) if specs else None


def refused(backend, status: int, obj, payload: dict) -> bool:
    """True when a host turned down the tool schemas this module sent.

    The host is remembered, so the caller rebuilds the request and it goes
    out in the text protocol, now and for the rest of the process.
    """
    if _ACTIVE.get() is None or status not in (400, 404, 422) or "tools" not in payload:
        return False
    from .endpoints import _error_message
    from .provider_fault_boundary import redacted_text
    message = _error_message(obj).lower()
    if "tool" not in message and "function" not in message:
        return False
    _NO_NATIVE.add((backend.base_url, backend.model))
    _LOG.warning("%s (%s) refused tool schemas with status %s: %s; using the text "
                 "protocol for this model", backend.name, backend.model, status,
                 redacted_text(message))
    return True


def canonical(prose: str, calls: list) -> str:
    """The reply as the text protocol writes it: prose, then one TOOL line per call."""
    if not calls:
        return prose
    lines = [f"TOOL {c['name']} {json.dumps(c['arguments'], ensure_ascii=False)}" for c in calls]
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


def absorb(dialect: str, backend, prose: str, calls: list, raw, claimed: bool) -> str:
    """Check a native reply, remember it, and return its text-protocol form."""
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
    text = canonical(prose, calls)
    if calls and raw is not None:
        box.remember(Reply(text, dialect, raw, [dict(c) for c in calls]))
    return text
