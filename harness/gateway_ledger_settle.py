"""gateway_ledger_settle.py -- unsettled calls: find them, and let an operator settle one.

A call has a started entry before the provider is contacted and an end entry
after (gateway_calls). A started entry with no end is an unsettled call: the
gateway stopped in between. Its reservation counts against its key until it
is settled.

  unsettled(found, home)   every started entry with no end, from the files:
                           `unsettled` when a gateway named it at a start or no
                           gateway is running, `open` while a running gateway
                           may still be making the call.
  report(calls)            the lines `flywheel gateway-ledger verify` prints.
  settle(home, call, ...)  `flywheel gateway-ledger settle CALL`. The operator
                           says what the provider billed (`--input`, `--output`,
                           read from the provider's usage page) or `--no-charge`.
                           The ledger gets `endpoint_call_settled` with the
                           call id and the key is charged that amount; the
                           reservation is then free. With no gateway running
                           the entry is appended here. With one running, only
                           it may append, so a request file is left in the
                           ledger folder and the gateway applies it at its next
                           model call (`sweep`).

Settling records the operator's statement. It is not checked against the
provider.
"""
from __future__ import annotations

import json
import logging
import os
import re

from . import gateway_ledger
from .gateway_calls import SETTLED, scan

_LOG = logging.getLogger(__name__)
_CALL = re.compile(r"[0-9a-f]{24}\Z")
_KEPT = ("endpoint", "interface", "prompt_sha", "key", "key_fp")
NOTE_LIMIT = 200


def running(home) -> bool:
    """Does a gateway process hold this home's ledger? (The writer lock is taken.)"""
    from .journey_lock import ExclusiveJourneyLock, JourneyLockBusy
    where = gateway_ledger.folder(home)
    if not where.is_dir():
        return False
    try:
        with ExclusiveJourneyLock.acquire(where / gateway_ledger.LOCK, 0.0):
            return False
    except JourneyLockBusy:
        return True
    except OSError:
        return True                     # cannot tell: do not call an open call unsettled


def unsettled(found: list, home) -> dict:
    return scan(found, running(home))


def report(calls: dict) -> str:
    """What `verify` says about calls with no end entry. Empty when there are none."""
    lines = []
    for state, said in (("unsettled", "UNSETTLED"), ("open", "open")):
        rows = {call: row for call, row in calls.items() if row["state"] == state}
        if not rows:
            continue
        for call, row in rows.items():
            meta = row["meta"]
            reserved = meta.get("reserved")
            lines.append(f"  {said} call {call}  key={meta.get('key', 'owner')}  "
                         f"endpoint={meta.get('endpoint')}  "
                         f"reserved={sum(reserved) if isinstance(reserved, list) else 0}")
        if state == "unsettled":
            lines.append(f"{len(rows)} unsettled call(s): each has a started entry and no end "
                         "entry, because the gateway stopped in between. The provider may "
                         "have billed it. Its reservation counts against its key until "
                         "`flywheel gateway-ledger settle CALL`.")
        else:
            lines.append(f"{len(rows)} call(s) open: started, with no end entry yet, while a "
                         "gateway is running (in flight, or waiting for the ledger to resume).")
    return "\n".join(lines)


def _entry(call: str, meta: dict, counts: "dict | None", note: str) -> dict:
    out = {name: meta[name] for name in _KEPT if name in meta}
    out.update({"call": call, "settled_by": "operator",
                "charged_tokens": sum(counts.values()) if counts else 0})
    if counts:
        out.update(input=counts["input"], output=counts["output"])
    if note:
        out["note"] = note[:NOTE_LIMIT]
    return out


def _charge(home, meta: dict, counts: "dict | None") -> str:
    """Debit the key the call belongs to. Returns what was done, in words."""
    if not counts or "key_fp" not in meta:
        return "nothing was charged"
    from . import gateway_key_gate
    keys = gateway_key_gate.open_keys(home)
    row = keys.rows().get(meta.get("key"))
    if row is None or row.get("fingerprint") != meta["key_fp"]:
        return f"key '{meta.get('key')}' no longer exists, so nothing was charged"
    keys.debit(meta["key"], counts, False)
    return f"key '{meta['key']}' was charged {sum(counts.values())} tokens"


def apply(ledger, call: str, counts: "dict | None", note: str) -> str:
    """Append the settled entry for an orphan of this ledger and charge its key."""
    from .gateway_turn import _APPEND
    with ledger.calls._lock:
        meta = ledger.calls.open.get(call) if call in ledger.calls.orphans else None
    if meta is None:
        raise ValueError(f"call {call} is not an unsettled call of this ledger")
    charged = _charge(ledger.home, meta, counts)
    with _APPEND:
        ledger.append(SETTLED, call, _entry(call, meta, counts, note))
    return charged


def sweep(ledger) -> None:
    """The running gateway applies the settle requests an operator left. Never raises."""
    where = gateway_ledger.folder(ledger.home)
    try:
        requests = sorted(where.glob("settle-*.json"))
    except OSError:
        return
    for path in requests:
        try:
            asked = json.loads(path.read_text(encoding="utf-8"))
            call, counts = str(asked.get("call")), asked.get("counts")
            if counts is not None:
                counts = {name: int(counts[name]) for name in ("input", "output")}
            done = apply(ledger, call, counts, str(asked.get("note") or ""))
            _LOG.warning("gateway ledger: call %s settled by the operator; %s", call, done)
        except Exception as exc:        # noqa: BLE001 - a bad request is dropped and logged
            _LOG.error("gateway ledger: settle request %s was not applied (%s: %s)",
                       path.name, type(exc).__name__, exc)
        try:
            os.unlink(path)
        except OSError:
            _LOG.error("gateway ledger: settle request %s could not be removed", path.name)


def settle(home, call: str, counts: "dict | None", note: str = "") -> tuple:
    """(text, exit code) for `flywheel gateway-ledger settle`."""
    if not _CALL.match(call or ""):
        return "a call id is 24 hexadecimal characters; `show --unsettled` lists them", 2
    found = gateway_ledger.check(home)
    row = unsettled(found, home).get(call)
    if row is None:
        return f"call {call} has an end entry or was never started; nothing to settle", 1
    if row["state"] != "unsettled":
        return (f"call {call} is open: a gateway is running and may still be making it. "
                "Settle it after that gateway has stopped or has named it unsettled"), 1
    if "key_fp" in row["meta"] and counts is None:
        return ("this call belongs to a gateway key: give --input N --output N (what the "
                "provider billed) or --no-charge"), 2
    try:
        ledger = gateway_ledger.GatewayLedger(home)
    except gateway_ledger.LedgerBusy:
        request = gateway_ledger.folder(home) / f"settle-{call}.json"
        temp = request.with_suffix(".tmp")
        temp.write_text(json.dumps({"call": call, "counts": counts or None, "note": note}),
                        encoding="utf-8")
        os.replace(temp, request)
        return (f"a gateway is running on this home, and only it appends to the ledger. The "
                f"request was left for it ({request.name}); it settles call {call} at its "
                "next model call"), 0
    try:
        done = apply(ledger, call, counts or None, note)
    finally:
        ledger.close()
    return f"call {call} settled; {done}", 0
