"""Dependency-free MCP stdio transport, with per-session negotiated sampling.

The reader queues incoming lines while a tool waits for sampling. Unrelated
requests are preserved for ordinary dispatch, and only a correlated response
can supply generated text. Tool implementations are shared with FastMCP.
"""
from __future__ import annotations

import io
import json
import sys
import queue
import threading
import time
from collections import deque

from . import __version__
from .mcp_server import do_check, do_fix, do_judge, do_polish, do_score, do_edit_plan, do_edit_submit
from .tool_meta import TOOLS_VAR, tool_set, offline, annotations, local_only_switch
from .tool_text import description
from . import house_tools as _house_tools, voice_tools as _voice_tools, tool_options
from . import dialogue_tools as _dialogue_tools

PROTOCOL = "2025-06-18"

_TEXT = {"text": {"type": "string", "description": "the passage to read"}}
_IS_HTML = {"is_html": {"type": "boolean", "default": False,
                        "description": "treat the input as HTML and preserve its markup"}}

# Host preparation and acceptance have no network or separate-model dependency.
LOCAL_ONLY = ("check", "score", "edit_plan", "edit_submit")
NEEDS_BACKEND = ()

_EDIT_OPTIONS = {'is_html': {'type': 'boolean',
             'default': False,
             'description': 'treat the input as HTML and preserve its markup'},
 'is_tex': {'type': 'boolean', 'default': False},
 'backend': {'type': 'string',
             'enum': ['auto',
                      'host',
                      'sampling',
                      'anthropic',
                      'claude-cli',
                      'openai',
                      'ollama',
                      'none']},
 'mode': {'type': 'string'},
 'profile': {'type': 'string'}}

TOOLS = [{'name': 'check',
  'description': description('check', {}),
  'inputSchema': {'type': 'object',
                  'required': ['text'],
                  'properties': {'text': {'type': 'string',
                                          'description': 'the passage to read'}}}},
 {'name': 'score',
  'description': description('score', {}),
  'inputSchema': {'type': 'object',
                  'required': ['text'],
                  'properties': {'text': {'type': 'string',
                                          'description': 'the passage to read'}}}},
 {'name': 'judge',
  'description': description('judge', {}),
  'inputSchema': {'type': 'object',
                  'required': ['text'],
                  'properties': {'text': {'type': 'string', 'description': 'the passage to read'},
                                 'is_html': {'type': 'boolean',
                                             'default': False,
                                             'description': 'treat the input as HTML and preserve '
                                                            'its markup'},
                                 'is_tex': {'type': 'boolean', 'default': False},
                                 'backend': {'type': 'string',
                                             'enum': ['auto',
                                                      'host',
                                                      'sampling',
                                                      'anthropic',
                                                      'claude-cli',
                                                      'openai',
                                                      'ollama',
                                                      'none']},
                                 'mode': {'type': 'string'},
                                 'profile': {'type': 'string'}}}},
 {'name': 'fix',
  'description': description('fix', {}),
  'inputSchema': {'type': 'object',
                  'required': ['text'],
                  'properties': {'text': {'type': 'string', 'description': 'the passage to read'},
                                 'is_html': {'type': 'boolean',
                                             'default': False,
                                             'description': 'treat the input as HTML and preserve '
                                                            'its markup'},
                                 'is_tex': {'type': 'boolean', 'default': False},
                                 'backend': {'type': 'string',
                                             'enum': ['auto',
                                                      'host',
                                                      'sampling',
                                                      'anthropic',
                                                      'claude-cli',
                                                      'openai',
                                                      'ollama',
                                                      'none']},
                                 'mode': {'type': 'string'},
                                 'profile': {'type': 'string'}}}},
 {'name': 'polish',
  'description': description('polish', {}),
  'inputSchema': {'type': 'object',
                  'required': ['text'],
                  'properties': {'text': {'type': 'string', 'description': 'the passage to read'},
                                 'bar': {'type': 'integer',
                                         'default': 4,
                                         'minimum': 1,
                                         'maximum': 5,
                                         'description': 'the quality bar every dimension must '
                                                        'clear'},
                                 'passes': {'type': 'integer',
                                            'default': 3,
                                            'minimum': 1,
                                            'description': 'how many rewrite attempts before '
                                                           'giving up'},
                                 'is_html': {'type': 'boolean',
                                             'default': False,
                                             'description': 'treat the input as HTML and preserve '
                                                            'its markup'},
                                 'is_tex': {'type': 'boolean', 'default': False},
                                 'backend': {'type': 'string',
                                             'enum': ['auto',
                                                      'host',
                                                      'sampling',
                                                      'anthropic',
                                                      'claude-cli',
                                                      'openai',
                                                      'ollama',
                                                      'none']},
                                 'mode': {'type': 'string'},
                                 'profile': {'type': 'string'}}}},
 {'name': 'edit_plan',
  'description': description('edit_plan', {}),
  'inputSchema': {'type': 'object',
                  'required': ['text'],
                  'properties': {'text': {'type': 'string', 'description': 'the passage to read'},
                                 'mode': {'type': 'string'},
                                 'profile': {'type': 'string'},
                                 'goal': {'type': 'string',
                                          'enum': ['fix', 'polish', 'judge'],
                                          'default': 'fix'},
                                 'is_tex': {'type': 'boolean', 'default': False},
                                 'is_html': {'type': 'boolean',
                                             'default': False,
                                             'description': 'treat the input as HTML and preserve '
                                                            'its markup'}}}},
 {'name': 'edit_submit',
  'description': description('edit_submit', {}),
  'inputSchema': {'type': 'object',
                  'required': ['text', 'rewrite', 'plan_id'],
                  'properties': {'text': {'type': 'string', 'description': 'the passage to read'},
                                 'rewrite': {'type': 'string'},
                                 'plan_id': {'type': 'string'},
                                 'scores': {'type': 'object'},
                                 'model': {'type': 'string'},
                                 'author_text': {'type': 'string'}}}},
 {'name': 'articulate.status',
  'description': description('articulate.status', {}),
  'inputSchema': {'type': 'object', 'properties': {}}},
 {'name': 'articulate.doctor',
  'description': description('articulate.doctor', {}),
  'inputSchema': {'type': 'object', 'properties': {}}}]


# Series, personal-voice and house-voice tools: local, read-only, defined beside their handlers.
TOOLS += _voice_tools.TOOLS + _house_tools.TOOLS + _dialogue_tools.TOOLS
LOCAL_ONLY += _voice_tools.NAMES + _house_tools.NAMES + _dialogue_tools.NAMES
TOOLS[0]["inputSchema"]["properties"]["max_hits"] = {
    "type": "integer", "default": 50, "minimum": 0, "maximum": 1000,
    "description": "Maximum span records; full-text verdict and scores are unchanged."}
for _tool in TOOLS[:2]:           # check and score
    _tool["inputSchema"]["properties"]["profile"] = {
        "type": "string",
        "description": "A register or domain profile, such as chat, readme or commit. "
                       "Pass chat when a model checks its own reply to a person: it adds "
                       "the structure rules. With no profile the default line rules run, "
                       "and the result's rules_run field says so."}
tool_options.extend(TOOLS)


def listed_tools(environ=None):
    return [dict(tool, description=description(tool["name"], environ),
                 title=annotations(tool["name"], environ)["title"],
                 annotations=annotations(tool["name"], environ)) for tool in TOOLS]


def _ok(rid, result):
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def _err(rid, code, message):
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def _valid_request_id(value) -> bool:
    return type(value) is str or type(value) is int


def _identity(include_detail: bool, session=None) -> dict:
    info = {"ok": True, "server": "articulate", "version": __version__,
            "protocol": PROTOCOL}
    if include_detail:
        info["tools"] = [t["name"] for t in listed_tools()]
        info["local_only"] = list(LOCAL_ONLY)
        info["needs_llm_backend"] = list(NEEDS_BACKEND)
        info["optional_llm_backend"] = ["judge", "fix", "polish"]
        info["sampling_advertised"] = bool(session and session.sampling_advertised)
        info["editor_default"] = "sampling" if info["sampling_advertised"] and not offline() else "host"
        info["tool_set"] = tool_set()
        info["hidden"] = []
        info["python"] = "%d.%d.%d" % sys.version_info[:3]
        info["local_only_switch"] = local_only_switch()
        info["offline_editors"] = offline()
    return info


def _text_arg(args: dict) -> str:
    text = args.get("text")
    if not isinstance(text, str):
        raise ValueError("'text' is required and must be a string")
    return text


def _call(params: dict, session=None) -> dict:
    name = params.get("name")
    args = params.get("arguments") or {}
    if not isinstance(args, dict):
        return {"content": [{"type": "text", "text": "'arguments' must be an object"}],
                "isError": True}
    if name in ("articulate.status", "articulate.doctor"):
        info = _identity(name == "articulate.doctor", session)
        return _tool_result(info)
    try:
        if name == "check":
            result = do_check(_text_arg(args), _max_hits(args), args.get("profile"))
        elif name == "score":
            named = () if args.get("profile") is None else (args["profile"],)
            result = do_score(_text_arg(args), *named)
        elif name in ("judge", "fix", "polish"):
            options = {key: args[key] for key in _EDIT_OPTIONS if key in args}
            if session is not None:
                options.update(sampling=session.sample, sampling_advertised=session.sampling_advertised)
            if name == "polish":
                options.update(bar=args.get("bar", 4), passes=args.get("passes", 3))
            options.update(tool_options.given(name, args))
            result = {"judge": do_judge, "fix": do_fix, "polish": do_polish}[name](_text_arg(args), **options)
        elif name == "edit_plan":
            result = do_edit_plan(_text_arg(args), **{key: args[key] for key in
                ("mode", "profile", "goal", "is_html", "is_tex") if key in args},
                **tool_options.given(name, args))
        elif name == "edit_submit":
            for key in ("rewrite", "plan_id"):
                if not isinstance(args.get(key), str):
                    raise ValueError("'%s' is required and must be a string" % key)
            result = do_edit_submit(_text_arg(args), args["rewrite"], args["plan_id"],
                                    scores=args.get("scores"), model=args.get("model"),
                                    author_text=args.get("author_text"),
                                    **tool_options.given(name, args))
        elif name in _dialogue_tools.NAMES:
            result = _dialogue_tools.handle(name, args)
        elif name in _voice_tools.NAMES or name in _house_tools.NAMES:
            result = (_voice_tools if name in _voice_tools.NAMES else _house_tools).handle(name, args)
        else:
            return {"content": [{"type": "text", "text": "unknown tool %r" % (name,)}],
                    "isError": True}
    except Exception as exc:          # a tool error is a result, not a dead server
        return {"content": [{"type": "text",
                             "text": "[error] %s: %s" % (type(exc).__name__, exc)}],
                "isError": True}
    return _tool_result(result)


def _max_hits(args):
    value = args.get("max_hits")
    if value is None:
        return 50
    if type(value) is not int or not 0 <= value <= 1000:
        raise ValueError("'max_hits' must be a whole number from 0 to 1000")
    return value


def _tool_result(result):
    out = {"content": [{"type": "text", "text": json.dumps(result, separators=(",", ":"), ensure_ascii=False)}]}
    if result.get("ok") is False:
        out["isError"] = True
    return out


def handle(req, session=None):
    """Map one JSON-RPC request to a response dict, or None for a notification."""
    if not isinstance(req, dict):
        return _err(None, -32600, "invalid request")
    rid = req.get("id") if "id" in req and _valid_request_id(req.get("id")) else None
    if "id" in req and not _valid_request_id(req["id"]):
        return _err(None, -32600, "invalid request")
    if req.get("jsonrpc") != "2.0":
        return _err(rid, -32600, "invalid request")
    method = req.get("method")
    if not isinstance(method, str):
        return _err(rid, -32600, "invalid request: method must be a string")
    if "id" not in req:
        return None
    if method == "initialize":
        if session is not None:
            params = req.get("params", {})
            if not isinstance(params, dict):
                return _err(rid, -32602, "invalid params")
            if session.initialized:
                return _err(rid, -32600, "session already initialized")
            capabilities = params.get("capabilities", {})
            if not isinstance(capabilities, dict):
                return _err(rid, -32602, "invalid capabilities")
            session.sampling_advertised = isinstance(capabilities.get("sampling"), dict)
            session.initialized = True
        return _ok(rid, {"protocolVersion": PROTOCOL, "capabilities": {"tools": {}},
                         "serverInfo": {"name": "articulate", "version": __version__}})
    if method == "ping":
        return _ok(rid, {})
    if method == "tools/list":
        return _ok(rid, {"tools": listed_tools()})
    if method == "tools/call":
        params = req["params"] if "params" in req else {}
        if not isinstance(params, dict):
            return _err(rid, -32602, "invalid params")
        return _ok(rid, _call(params, session))
    return _err(rid, -32601, "method not found: %s" % (method,))


# Sibling lane servers are split on what they call this function. Measured across
# the installed distributions on 2026-09-22: chorus, gather, mneme and
# accountable-surface expose handle_request; plexus, canon and relay expose
# handle. Nothing dispatches across packages by either name, so neither is a
# contract and this alias is a convenience, not a requirement. Both point at one
# function, so there is no second code path to keep in step.
handle_request = handle


class Session:
    """One stdio connection; never share capabilities or outstanding replies."""
    def __init__(self, stdin, stdout, sampling_timeout=60):
        self.stdin, self.stdout = stdin, stdout
        self.sampling_timeout = sampling_timeout
        self.incoming = queue.Queue()
        self.pending = deque()
        self.initialized = False
        self.sampling_advertised = False
        self.counter = 0
        self.closed = False

    def send(self, message):
        self.stdout.write(json.dumps(message) + "\n")
        self.stdout.flush()

    def read(self):
        try:
            for line in self.stdin:
                if not line.strip():
                    continue
                try:
                    self.incoming.put(json.loads(line))
                except (ValueError, RecursionError):
                    self.incoming.put(_ParseError())
        finally:
            self.incoming.put(_EndOfInput())

    def sample(self, instructions, text, timeout):
        if not self.initialized or not self.sampling_advertised:
            raise RuntimeError("sampling was not advertised by this client")
        self.counter += 1
        rid = "articulate-sampling-%d" % self.counter
        deadline = time.monotonic() + min(timeout, self.sampling_timeout)
        self.send({"jsonrpc": "2.0", "id": rid, "method": "sampling/createMessage",
                   "params": {"messages": [{"role": "user", "content": {"type": "text", "text": text}}],
                              "systemPrompt": instructions, "maxTokens": 4096, "includeContext": "none"}})
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("sampling timed out")
            try:
                message = self.incoming.get(timeout=remaining)
            except queue.Empty:
                raise RuntimeError("sampling timed out") from None
            if isinstance(message, _EndOfInput):
                self.closed = True
                raise RuntimeError("sampling client disconnected")
            if isinstance(message, dict) and "method" not in message and message.get("id") == rid:
                if message.get("jsonrpc") != "2.0" or "error" in message:
                    raise RuntimeError("sampling request failed")
                result = message.get("result")
                if not isinstance(result, dict):
                    raise RuntimeError("sampling returned an invalid result")
                content = result.get("content")
                if not isinstance(content, dict) or content.get("type") != "text" or not isinstance(content.get("text"), str):
                    raise RuntimeError("sampling did not return text")
                if not isinstance(result.get("model"), str):
                    raise RuntimeError("sampling did not name its model")
                return result
            # Responses with another id are stale/unrelated and cannot be used.
            if not (isinstance(message, dict) and "method" not in message and
                    ("result" in message or "error" in message)):
                self.pending.append(message)


class _ParseError:
    pass


class _EndOfInput:
    pass


def _utf8(stream, **options):
    try:
        stream.reconfigure(encoding="utf-8", **options)
    except (AttributeError, ValueError, io.UnsupportedOperation) as exc:
        sys.stderr.write("articulate-mcp: could not switch %s to UTF-8 (%s); non-ASCII text may be misread\n"
                         % (getattr(stream, "name", "a stream"), exc))
    return stream


def serve(stdin=None, stdout=None, *, sampling_timeout=60) -> int:
    session = Session(stdin if stdin is not None else _utf8(sys.stdin, errors="replace"),
                      stdout if stdout is not None else _utf8(sys.stdout, newline="\n"), sampling_timeout)
    reader = threading.Thread(target=session.read, daemon=True)
    reader.start()
    while session.pending or not session.closed:
        req = session.pending.popleft() if session.pending else session.incoming.get()
        if isinstance(req, _EndOfInput):
            session.closed = True
            continue
        if isinstance(req, _ParseError):
            session.send(_err(None, -32700, "parse error"))
            continue
        # A late sampling response is not a new JSON-RPC request.
        if isinstance(req, dict) and "method" not in req and ("result" in req or "error" in req):
            continue
        try:
            resp = handle(req, session)
        except Exception as exc:
            sys.stderr.write("articulate-mcp: internal error (%s)\n" % type(exc).__name__)
            if not isinstance(req, dict) or "id" not in req:
                continue
            rid = req["id"] if _valid_request_id(req["id"]) else None
            resp = _err(rid, -32603, "internal error (%s)" % type(exc).__name__)
        if resp is not None:
            session.send(resp)
    return 0


def main() -> int:
    return serve()


if __name__ == "__main__":
    raise SystemExit(main())
