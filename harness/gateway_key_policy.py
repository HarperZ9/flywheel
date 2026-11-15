"""gateway_key_policy.py -- what one virtual key may ask for, beyond its totals.

A key's totals are checked before a call and debited after it. Three things
that check alone does not bound are bounded here.

  calls in flight   `admit` counts the calls a key has running in this gateway
                    and refuses a new one at the key's limit (`in_flight`,
                    default 4) with 429. It also reserves each running call's
                    output limit, plus a quarter of its request size in bytes
                    as input, and refuses a new call when the totals plus the
                    reservations of the calls already running reach a limit.
                    `release` frees the slot and the reservation.
  output per call   `capped` refuses a `max_tokens` (Messages) or
                    `max_output_tokens` (Responses) over the key's
                    `max_output`, naming the field.
  pass-through      `passthrough` runs when a Messages request is about to be
                    forwarded as sent to an Anthropic upstream. Each
                    `anthropic-beta` value must be on the key's `betas` list,
                    each tool with a `type` other than `custom` on its
                    `server_tools` list (by full type, or by the name before
                    the date suffix), and `mcp_servers` needs `mcp`. A new key
                    has none of them. `*` on a list allows everything.

  suspension        `suspend` stops a key, in this process and in the key
                    list, until `flywheel gateway-key clear NAME`. One rule
                    decides when: a call of the key reached the provider and
                    was not fully accounted, which means its debit or its
                    ledger entry failed, for any reason, whether or not the
                    reply was delivered (gateway_unaccounted, gateway_account).

The gateway token is the owner and is never limited here. The counts are held
in this process: two gateways on two machines do not share them.

What the reservation leaves open, exactly: a call that runs alone is admitted
whenever the totals are under the limit, so it can cross by its own cost
(input plus up to its output limit). Calls that run together can cross by the
input each one used beyond a quarter of its request bytes, summed over at
most `in_flight` calls, plus that one call's cost.
"""
from __future__ import annotations

import copy
import logging
import threading
import time

from . import gateway_keys

_LOG = logging.getLogger(__name__)
DEFAULT_IN_FLIGHT = 4
_HELD, _HELD_LOCK = {}, threading.Lock()    # key fingerprint -> (when it was stopped, why)
DEFAULT_OUTPUT = 4096                   # reserved when a request names no output limit
_LOCK, _RUNNING = threading.RLock(), {}     # key fingerprint -> [[input, output], ...]
# Held by gateway_key_gate.enter from the second read of a key's row to `admit`.
# `release` takes the same lock, so a call cannot leave between the two.
ADMISSION = _LOCK
LISTS = {"betas": "--allow-beta", "server_tools": "--allow-server-tool"}


def _output(path: str, body) -> tuple:
    """(field name, the output limit the request asks for, or None)."""
    field = "max_output_tokens" if path == "/v1/responses" else "max_tokens"
    asked = body.get(field) if isinstance(body, dict) else None
    return field, asked if type(asked) is int and asked > 0 else None


def capped(caller, path: str, body) -> "tuple | None":
    """(reason, status, sentence, field) when the request asks for more output than
    the key allows in one call."""
    cap = caller.row.get("max_output")
    field, asked = _output(path, body)
    wanted = asked if asked is not None else (DEFAULT_OUTPUT if field != "max_tokens" else None)
    if cap is None or wanted is None or wanted <= cap:
        return None
    how = f"asked for {asked}" if asked is not None else f"named none, which sends {wanted}"
    return "max_output_exceeded", 400, (
        f"{field}: gateway key '{caller.name}' allows at most {cap} output tokens in one "
        f"call and the request {how}; send {field} at or under {cap}"), field


def admit(caller, path: str, body, size: int) -> "tuple | None":
    """Take a slot and a reservation for this call, or say why not.

    Returns None when the call may run (`caller.ticket` then holds what
    `release` frees), else (reason, 429, sentence, None)."""
    row, name = caller.row, caller.name
    limit = row.get("in_flight") or DEFAULT_IN_FLIGHT
    mine = [max(0, int(size)) // 4, _output(path, body)[1] or DEFAULT_OUTPUT]
    with _LOCK:
        running = _RUNNING.setdefault(caller.fingerprint, [])
        if len(running) >= limit:
            return "key_in_flight_limit", 429, (
                f"gateway key '{name}' already has {len(running)} calls in flight, its "
                "limit; retry when one finishes"), None
        if running:
            ahead = copy.deepcopy(row)
            for held_in, held_out in running:
                ahead["totals"]["input_tokens"] += held_in
                ahead["totals"]["output_tokens"] += held_out
                ahead["totals"]["tokens"] += held_in + held_out
            over = gateway_keys.over(ahead)
            if over is not None:
                return "key_budget_reserved", 429, (
                    f"the calls gateway key '{name}' has in flight reserve the rest of its "
                    f"{over[0].replace('_', ' ')}; retry when one finishes"), None
        running.append(mine)
    caller.ticket = mine
    return None


def release(caller) -> None:
    """Free the slot and reservation `admit` took. Safe to call when none was taken."""
    ticket, caller.ticket = getattr(caller, "ticket", None), None
    if ticket is None:
        return
    with _LOCK:
        running = _RUNNING.get(caller.fingerprint) or []
        for index, held in enumerate(running):
            if held is ticket:
                del running[index]
                break
        if not running:
            _RUNNING.pop(caller.fingerprint, None)


def _listed(allowed, value: str, by_family: bool = False) -> bool:
    for entry in allowed or []:
        if entry == "*" or entry == value or (by_family and value.startswith(f"{entry}_")):
            return True
    return False


def passthrough(caller, body, headers) -> "tuple | None":
    """(field, what) for the first thing in a pass-through request the key may not send."""
    row = caller.row
    for value in str((headers or {}).get("anthropic-beta") or "").split(","):
        if value.strip() and not _listed(row.get("betas"), value.strip()):
            return "anthropic-beta", (f"the value {value.strip()[:80]!r}",
                                      f"--allow-beta {value.strip()[:80]}")
    tools = body.get("tools") if isinstance(body, dict) else None
    for index, tool in enumerate(tools if isinstance(tools, list) else []):
        kind = tool.get("type") if isinstance(tool, dict) else None
        if isinstance(kind, str) and kind != "custom" and not _listed(
                row.get("server_tools"), kind, by_family=True):
            return f"tools.{index}.type", (f"the provider-defined tool {kind[:80]!r}",
                                           f"--allow-server-tool {kind[:80]}")
    if isinstance(body, dict) and body.get("mcp_servers") and not row.get("mcp"):
        return "mcp_servers", ("MCP servers the provider connects to", "--allow-mcp")
    return None


def refusal_text(caller, found: tuple) -> str:
    field, (what, flag) = found
    return (f"{field}: gateway key '{caller.name}' may not send {what} to the provider. "
            f"Allow it with `flywheel gateway-key set {caller.name} {flag}`, or use the "
            "gateway token. Nothing was sent upstream.")


def check_passthrough(caller, body, headers, ledger, interface: str) -> None:
    """Refuse a request field this key may not forward to an Anthropic upstream.

    Raises TurnRefused("forbidden") naming the field, after appending
    `endpoint_call_refused`. The owner forwards everything."""
    if caller is None or caller.row is None:
        return
    from .gateway_turn import _APPEND, TurnRefused
    found = passthrough(caller, body, headers)
    if found is None:
        return
    _LOG.info("gateway %s request refused for key %s (field_not_allowed: %s)", interface,
              caller.name, found[0])
    if ledger is not None:
        with _APPEND:
            ledger.append("endpoint_call_refused", "field_not_allowed", {
                "interface": interface, **caller.meta, "reason": "field_not_allowed",
                "field": found[0]})
    raise TurnRefused("forbidden", refusal_text(caller, found))


def suspend(caller, reason: str) -> str:
    """Stop a key until an operator clears it; returns the sentence that says so.

    The stop is held in this process and written to the key list. When the
    list cannot be written (the usual reason a charge failed), the stop still
    holds for the life of this gateway and the failure is logged."""
    if caller.row is None:
        return ""
    now = time.time()
    with _HELD_LOCK:
        _HELD[caller.fingerprint] = (now, reason)
    try:
        caller.keys.mark(caller.name, suspended={"reason": reason, "at": int(now)})
    except Exception as exc:  # noqa: BLE001 - the in-process stop stands either way
        _LOG.error("gateway key %s is suspended in this gateway process only: the key list "
                   "could not be written (%s)", caller.name, type(exc).__name__)
    return (f"; gateway key '{caller.name}' is suspended until an operator runs "
            f"`flywheel gateway-key clear {caller.name}`")


def suspended(caller) -> "str | None":
    """Why a key is stopped, or None. `flywheel gateway-key clear` lifts both forms."""
    row = caller.row
    if isinstance(row.get("suspended"), dict):
        return str(row["suspended"].get("reason") or "suspended")
    with _HELD_LOCK:
        held = _HELD.get(caller.fingerprint)
        if held is not None and (row.get("cleared") or 0) >= held[0]:
            del _HELD[caller.fingerprint]
            held = None
    return None if held is None else held[1]


def fields(args) -> dict:
    """The row fields a `create` or `set` command line asks for. Raises KeysError."""
    out = {}
    for name, flag in (("in_flight", "--in-flight"), ("max_output", "--max-output")):
        value = getattr(args, name, None)
        if value is not None:
            if value < 1:
                raise gateway_keys.KeysError(f"{flag} must be a whole number, one or more")
            out[name] = value
    for name in LISTS:
        value = getattr(args, name, None)
        if value is not None:
            out[name] = sorted({part.strip() for part in value.split(",") if part.strip()})
    if getattr(args, "mcp", None):
        out["mcp"] = True
    return out


def describe(row: dict) -> list:
    """The lines `flywheel gateway-key show` prints for these controls."""
    return [f"in flight     {row.get('in_flight') or DEFAULT_IN_FLIGHT} calls at once",
            f"max output    {row.get('max_output') or 'no cap'} tokens in one call",
            f"betas         {', '.join(row.get('betas') or []) or 'none'} (anthropic-beta "
            "values the key may send)",
            f"server tools  {', '.join(row.get('server_tools') or []) or 'none'} "
            "(provider-defined tool types the key may send)",
            f"mcp servers   {'allowed' if row.get('mcp') else 'not allowed'}"]
