"""gateway_reach.py -- in a gateway process, a model call leaves only inside an account.

Until 2.0.0's sixth review round the gateway ledger was passed by hand to the
routes that were known to reach a provider. Seven routes were missed
(/api/eval/run, /api/audit/run, /api/bench/run, /api/workflow, /api/plan/run,
/api/capability and the legacy /api/subagents/spawn body): they built a
proposer with no ledger and their calls left no entry. A list of call sites
kept by hand cannot rule that out, so the rule now sits at the transports.

  enforce(ledger_of)   called once when a process becomes a gateway
                       (gateway_ledger_gate.startup). From then on:
  ledger()             what a proposer factory uses when it was given no
                       ledger: the gateway's, or LedgerUnavailable. Outside a
                       gateway process it is None and the proposer is bare.
  check(what)          called by every transport that sends a model request
                       (endpoints_http.send and _guard, the command-line
                       backends, the proposers). In a gateway process it
                       raises `Unaccounted`, before anything is sent, unless
                       the thread is inside `gateway_account.Call.reach`
                       (a started entry is on disk), inside
                       `gateway_account.unbilled` (token counting), or inside
                       one of the two named exceptions below.
  traced(send)         a gateway agent run: its own trace holds a started
                       record before each request (gateway_agent_transport).
  local_model(send)    the model server on this machine, reached through the
                       chat path's local names or the raw proxy. It has no
                       provider account and is outside the ledger
                       (docs/KNOWN-LIMITS-2.0.0.md).
  at(path) / route()   the gateway route this thread is serving, written into
                       the entries of a call made for it.

`check` fails closed. A route added later that reaches a provider with no
account answers an error and sends nothing; it cannot bill a call the ledger
does not hold. tests/test_gateway_route_reach.py exercises every route of the
gateway against a counting upstream with this rule on.
"""
from __future__ import annotations

import contextvars
import logging

_LOG = logging.getLogger(__name__)
_LEDGER_OF = None
_ROUTE = contextvars.ContextVar("flywheel_gateway_route", default="")
_EXEMPT = contextvars.ContextVar("flywheel_gateway_exempt", default="")
TRACED, LOCAL = "traced", "local_model"
TEXT = ("a model request was about to leave this gateway outside its accounting, so it "
        "was refused and nothing was sent upstream")


class Unaccounted(RuntimeError):
    """A provider contact was attempted in a gateway process with no account open."""


def enforce(ledger_of) -> None:
    """This process serves the gateway: `ledger_of()` is its ledger, or None."""
    global _LEDGER_OF
    _LEDGER_OF = ledger_of


def release():
    """Stop enforcing and return what was enforced (for a test that restores it)."""
    global _LEDGER_OF
    was, _LEDGER_OF = _LEDGER_OF, None
    return was


def enforced() -> bool:
    return _LEDGER_OF is not None


def at(path: str) -> None:
    _ROUTE.set(str(path or ""))


def route() -> str:
    return _ROUTE.get()


def ledger():
    """The gateway's ledger for a call that was given none; None outside a gateway."""
    if _LEDGER_OF is None:
        return None
    from .gateway_ledger_gate import required
    return required(_LEDGER_OF)


def check(what: str) -> None:
    """Refuse a model request that is leaving a gateway process outside an account."""
    if _LEDGER_OF is None or _EXEMPT.get():
        return
    from .gateway_account import contacting
    if contacting() is not None:
        return
    _LOG.error("GATEWAY: a model request to %s on route %s was refused before it was sent: "
               "no ledger account was open for it", what, _ROUTE.get() or "(unknown)")
    raise Unaccounted(f"{TEXT} ({what})")


def _exempt(mark: str, send):
    token = _EXEMPT.set(mark)
    try:
        return send()
    finally:
        _EXEMPT.reset(token)


def traced(send):
    """Run `send` for a gateway agent run, whose trace records the request first."""
    return _exempt(TRACED, send)


def local_model(send):
    """Run `send` against the model server on this machine."""
    return _exempt(LOCAL, send)
