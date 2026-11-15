"""gateway_ledger_relay.py -- a gateway's child process records its model calls in the gateway's ledger.

One process writes a home's ledger (gateway_ledger). The worker of a v1
subagent swarm (`python -m harness.subagent_worker`) is a child process that
runs a model, so it cannot append. Until 2.0.0's sixth review round its calls
left no gateway-ledger entry at all.

  parent   `issue(env)` starts, once, a listener on a loopback port and puts
           its address and a fresh token for one child into `env`. The child
           sends one JSON line per entry; the parent appends it to the
           gateway ledger under the same lock as its own calls and answers
           only after the append returned, which is after the commit to the
           disk. So the write-ahead rule holds across the process boundary:
           the child's request leaves after its started entry is on disk.
           `closed(token)` is called when the child has ended: a call it
           started and never ended is named unsettled at once
           (gateway_calls.abandon).
  child    `adopt(environ)` makes the child a gateway process whose ledger is
           `RelayLedger`: every proposer it builds is recorded and every
           transport refuses a request outside an account (gateway_reach).
           The two variables are removed from the environment, so a tool the
           agent runs does not inherit them.

A child may append three kinds only: a started entry, and one `endpoint_call`
or `endpoint_call_failed` for a call that same child started. Anything else
is refused. Of an entry's meta the parent keeps the fields a call made with
the gateway token has (FIELDS) and drops the rest, so a child cannot write a
key's name, a fingerprint or a reservation into the ledger and have it
counted against that key. When the parent cannot append (no ledger, a full
disk) the child is told, its call is refused and nothing is sent.
"""
from __future__ import annotations

import json
import logging
import secrets
import socket
import socketserver
import threading

from . import gateway_calls as _calls

_LOG = logging.getLogger(__name__)
ADDR, TOKEN = "FLYWHEEL_GATEWAY_LEDGER_RELAY", "FLYWHEEL_GATEWAY_LEDGER_RELAY_TOKEN"
ENDS = ("endpoint_call", "endpoint_call_failed")
LIMIT = 64 * 1024                       # one entry line
FIELDS = ("endpoint", "prompt_sha", "call", "route", "model_ref", "seed", "response_sha",
          "reason", "error")            # what a child's entry may say
VIA = "subagent_worker"
_LOCK = threading.Lock()
_SERVER = None
_CHILDREN: dict = {}                    # token -> the calls that child started and has not ended


class RelayRefused(RuntimeError):
    """The parent gateway did not append the entry."""


def _append(token: str, kind: str, content: str, meta: dict) -> None:
    from . import gateway_reach
    from .gateway_turn import _APPEND
    call = meta.get("call") if isinstance(meta, dict) else None
    if not isinstance(call, str) or not call or not isinstance(content, str):
        raise ValueError("an entry names its call")
    with _LOCK:
        started = _CHILDREN.get(token)
        if started is None:
            raise PermissionError("unknown relay token")
        if kind == _calls.STARTED:
            if content != call or call in started:
                raise ValueError("a started entry opens one new call")
        elif kind not in ENDS or call not in started:
            raise ValueError("a child ends only a call it started")
    ledger = gateway_reach.ledger()
    if ledger is None:
        raise RelayRefused("the gateway ledger is unavailable")
    kept = {name: meta[name] for name in FIELDS
            if isinstance(meta.get(name), (str, int)) and len(str(meta[name])) <= 400}
    with _APPEND:
        ledger.append(kind, content, {**kept, "via": VIA})
    with _LOCK:
        if kind == _calls.STARTED:
            started.add(call)
        else:
            started.discard(call)


class _Handler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            self.connection.settimeout(30)
            line = self.rfile.readline(LIMIT + 1)
            if len(line) > LIMIT:
                raise ValueError("entry too large")
            asked = json.loads(line)
            _append(str(asked["token"]), str(asked["kind"]), asked["content"], asked["meta"])
            answer = {"ok": True}
        except Exception as exc:    # noqa: BLE001 - the child is told; its call is not sent
            _LOG.error("gateway ledger relay refused an entry (%s)", type(exc).__name__)
            answer = {"ok": False, "error": type(exc).__name__}
        try:
            self.wfile.write(json.dumps(answer).encode() + b"\n")
        except OSError:
            pass


class _Server(socketserver.ThreadingTCPServer):
    daemon_threads, allow_reuse_address = True, False


def issue(env: dict) -> str:
    """Give one child a token and the listener's address in `env`; returns the token.

    Outside a gateway process nothing is issued and "" is returned."""
    from . import gateway_reach
    global _SERVER
    if not gateway_reach.enforced():
        return ""
    with _LOCK:
        if _SERVER is None:
            _SERVER = _Server(("127.0.0.1", 0), _Handler)
            threading.Thread(target=_SERVER.serve_forever, daemon=True,
                             name="gateway-ledger-relay").start()
        token = secrets.token_hex(32)
        _CHILDREN[token] = set()
        env[ADDR] = "127.0.0.1:%d" % _SERVER.server_address[1]
        env[TOKEN] = token
    return token


def closed(token: str) -> list:
    """The child with `token` has ended. Returns the calls it left without an end entry,
    each now named unsettled in the ledger."""
    from . import gateway_reach
    with _LOCK:
        left = sorted(_CHILDREN.pop(token, ()) or ())
    if left:
        try:
            _calls.abandon(gateway_reach.ledger(), left, "child_ended")
        except Exception as exc:    # noqa: BLE001 - the started entries remain; verify names them at restart
            _LOG.error("gateway ledger relay could not mark %d call(s) of an ended child "
                       "unsettled (%s)", len(left), type(exc).__name__)
    return left


class RelayLedger:
    """The ledger of a gateway's child process: each append is made by the parent."""

    def __init__(self, addr: str, token: str):
        host, _, port = addr.rpartition(":")
        self._where, self._token = (host, int(port)), token

    def append(self, kind: str, content: str, meta: dict):
        line = json.dumps({"token": self._token, "kind": kind, "content": content,
                           "meta": meta}).encode() + b"\n"
        if len(line) > LIMIT:
            raise RelayRefused("entry too large")
        with socket.create_connection(self._where, timeout=30) as conn:
            conn.sendall(line)
            answer = json.loads(conn.makefile("rb").readline(4096) or b"{}")
        if answer.get("ok") is not True:
            raise RelayRefused(str(answer.get("error") or "no answer"))


def adopt(environ) -> bool:
    """In a child: record through the parent gateway when it issued a relay. True if so."""
    addr, token = environ.pop(ADDR, ""), environ.pop(TOKEN, "")
    if not addr or not token:
        return False
    from . import gateway_reach
    ledger = RelayLedger(addr, token)
    gateway_reach.enforce(lambda: ledger)
    return True
