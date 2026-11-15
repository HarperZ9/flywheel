"""gateway_calls.py -- write-ahead accounting: a call is in the ledger before it is made.

Until 2.0.0's fifth review round the ledger entry of a model call was written
after the provider answered, because it holds the hash of the reply. A gateway
process that was killed between the two left a billed call with no entry.

Now every call that will contact a provider has two entries:

  endpoint_call_started   appended and committed to the disk before the request
                          leaves (`begin`, called by `gateway_account.Call.reach`
                          at first contact). content: the call id. meta: the
                          route (`endpoint`, `interface`), the request hash
                          (`prompt_sha`), the caller (`key`, `key_fp`), `call`,
                          and for a virtual key `reserved`: the input and output
                          tokens the call reserved at admission.
  the end entry           `endpoint_call` or `endpoint_call_failed`, as before,
                          with the same `call` in its meta.

The invariant: no request reaches a provider unless its started entry is in
the ledger. A started entry with no end entry is an unsettled call: the
gateway stopped after the entry was committed. The provider may have been
contacted and may have billed it; the entry is written before contact, so it
can also be a call that was never sent.

  Calls      what a `GatewayLedger` knows about calls with no end entry. At
             open, every such call in the last segment (or carried in its
             header from the segment before) is an orphan: one gateway writes
             a home's ledger, so the process that started them is gone. The
             ledger then appends `calls_unsettled` naming them.
  held       the reservations of a key's unsettled calls. The key gate adds
             them to the key's totals, so they count as spent until an
             operator settles the call (`flywheel gateway-ledger settle`).
  defer      keeps an end entry whose append failed. A ledger that stopped
             taking writes appends it when it resumes, after `ledger_gap`,
             marked `late`: the calls that were in flight when the write
             failed are then recorded with their real end.
  abandon    names a call of a running gateway unsettled at once, with a
             `calls_unsettled` entry: a call that ended with no end entry and
             none kept for later, or a call a child process left behind.
  scan       the same reading from the files alone, for the command line.
  audit      the rules a call record keeps, checked from the entries alone:
             only an end entry closes a call, and an end with no start, a
             second end, a repeated start and an end that differs from its
             start on the route, the request or the caller are findings.
             `flywheel gateway-ledger verify` and the tests' `recorded` helper
             both call it, so the tool and the tests cannot disagree.
"""
from __future__ import annotations

import logging
import threading
import uuid

_LOG = logging.getLogger(__name__)
STARTED, SETTLED, MARKER = "endpoint_call_started", "endpoint_call_settled", "calls_unsettled"
NOT_SENT = "not_sent"                   # the end of a call whose start could not be committed
ENDS = ("endpoint_call", "endpoint_call_failed", SETTLED)   # the kinds that close a call
SAME = ("endpoint", "interface", "prompt_sha", "key", "key_fp")     # a start and its end agree
TEXT = ("the gateway ledger could not record the start of this call, so the call was "
        "refused and nothing was sent upstream")


def begin(ledger, base: dict, reserved=None) -> str:
    """Append the started entry of one call and return the call id.

    Raises whatever the ledger raises. The caller sends nothing then."""
    from .gateway_turn import _APPEND
    call = uuid.uuid4().hex[:24]
    meta = {**base, "call": call}
    if reserved:
        meta["reserved"] = [int(reserved[0]), int(reserved[1])]
    with _APPEND:
        ledger.append(STARTED, call, meta)
    return call


class Calls:
    """Calls with a started entry and no end entry, for one open ledger."""

    def __init__(self, header=None, entries=()):
        self.open, self.orphans, self.late = {}, set(), []
        self._lock = threading.Lock()
        carried = (header or {}).get("open_calls")
        for call, meta in (carried if isinstance(carried, dict) else {}).items():
            self.open[call] = meta
        for entry in entries:
            self.note(entry)
        self.orphans = set(self.open)   # their gateway process is gone

    def note(self, entry) -> None:
        """Take one appended entry into account."""
        with self._lock:
            if entry.kind == STARTED:
                self.open[entry.content] = entry.meta
            elif entry.kind in ENDS:
                call = entry.meta.get("call")
                if self.open.pop(call, None) is not None:
                    self.orphans.discard(call)

    def carried(self) -> dict:
        """The header field a new segment carries: the calls still open before it."""
        with self._lock:
            return {"open_calls": dict(self.open)} if self.open else {}

    def announce(self, ledger) -> None:
        """At open: one `calls_unsettled` entry that names the orphans found."""
        with self._lock:
            found = sorted(self.orphans)
        if found:
            _LOG.error("GATEWAY LEDGER: %d call(s) were started and have no end entry; the "
                       "gateway that made them stopped first. Their reservations count "
                       "against their keys. Run `flywheel gateway-ledger show --unsettled`.",
                       len(found))
            ledger.append(MARKER, "found_at_start", {"reason": "found_at_start", "calls": found})

    def orphan(self, call: str) -> None:
        """A call of this process that ended with no end entry and none kept for later."""
        with self._lock:
            if call in self.open:
                self.orphans.add(call)

    def held(self, fingerprint: str) -> tuple:
        """(input, output, calls) reserved by the unsettled calls of one key."""
        with self._lock:
            rows = [self.open[call].get("reserved") for call in self.orphans
                    if self.open[call].get("key_fp") == fingerprint]
        rows = [row for row in rows if isinstance(row, list) and len(row) == 2]
        return sum(row[0] for row in rows), sum(row[1] for row in rows), len(rows)

    def flush(self, ledger, unconfirmed=()) -> None:
        """After a resume: end the starts that were never sent, append the kept ends."""
        for entry in unconfirmed:       # on disk although its append raised
            self.note(entry)
            if entry.kind == STARTED:   # its caller was refused: nothing was sent
                self.late.insert(0, ("endpoint_call_failed", NOT_SENT, {
                    **{k: v for k, v in entry.meta.items() if k != "reserved"},
                    "reason": NOT_SENT}))
        while self.late:
            kind, content, meta = self.late[0]
            ledger.append(kind, content, {**meta, "late": True})
            del self.late[0]


def of(ledger) -> "Calls | None":
    """The `Calls` of a ledger that keeps them (the on-disk one), else None."""
    found = getattr(ledger, "calls", None)
    return found if isinstance(found, Calls) else None


def held(ledger, fingerprint: str) -> tuple:
    found = of(ledger)
    return found.held(fingerprint) if found is not None else (0, 0, 0)


def defer(ledger, kind: str, content: str, meta: dict) -> None:
    """Keep an end entry the ledger refused, so the call is not left without one.

    A ledger whose writes failed appends it at its resume. A ledger that takes
    writes and refused this entry for another reason leaves the call unsettled."""
    found, call = of(ledger), meta.get("call")
    if found is None or not call:
        return
    if getattr(ledger, "failed", None) is not None:
        found.late.append((kind, content, dict(meta)))
    else:
        abandon(ledger, [call], "ended_without_entry")


def abandon(ledger, calls, reason: str) -> None:
    """Name open calls of a running gateway unsettled: held against their keys from now,
    and written down, so `verify` in another process reports them and `settle` takes them.
    When the entry cannot be written the calls are still held in this process."""
    found = of(ledger)
    if found is None:
        return
    with found._lock:
        named = sorted(call for call in calls if call in found.open)
        found.orphans.update(named)
    if named:
        _LOG.error("GATEWAY LEDGER: %d call(s) have no end entry (%s). Their reservations "
                   "count against their keys until they are settled.", len(named), reason)
        try:
            from .gateway_turn import _APPEND
            with _APPEND:
                ledger.append(MARKER, reason, {"reason": reason, "calls": named})
        except Exception as exc:        # noqa: BLE001 - the ledger is failing; a restart names them
            _LOG.error("gateway ledger could not record the unsettled call(s) (%s)",
                       type(exc).__name__)


def audit(rows, carried=None) -> tuple:
    """(open, findings) for entries in ledger order.

    `rows` yields (kind, content, meta, where). `open` maps the call id of each
    started entry with no end entry to {"meta", "where"}. A finding is
    (code, call, where, text); the codes are `malformed_start`,
    `repeated_start`, `end_without_start`, `second_end` and
    `end_differs_from_start`."""
    open_, ended, findings = dict(carried or {}), set(), []
    for kind, content, meta, where in rows:
        meta = meta if isinstance(meta, dict) else {}
        call = meta.get("call")
        if kind == STARTED:
            if content != call:
                findings.append(("malformed_start", str(content), where,
                                 "a started entry whose content is not its call id"))
            if content in open_ or content in ended:
                findings.append(("repeated_start", str(content), where,
                                 "a second started entry with the call id of an earlier one"))
            else:
                open_[content] = {"meta": meta, "where": where}
        elif kind in ENDS:
            first = open_.pop(call, None) if isinstance(call, str) else None
            if first is None:
                again = isinstance(call, str) and call in ended
                findings.append(("second_end" if again else "end_without_start", str(call),
                                 where, f"{kind} for a call that already has an end entry"
                                 if again else f"{kind} with no started entry before it"))
                continue
            ended.add(call)
            differ = [name for name in SAME if first["meta"].get(name) != meta.get(name)]
            if differ:
                findings.append(("end_differs_from_start", call, where,
                                 f"{kind} whose {', '.join(differ)} differ from its start"))
    return open_, findings


def _walk(found: list) -> tuple:
    """(open, marked, findings) over `gateway_ledger.check`'s result, every segment in order."""
    open_, marked, findings = {}, set(), []

    def rows(segment):
        for entry in segment["rows"]:
            if entry.kind == MARKER:
                marked.update(entry.meta.get("calls") or [])
            yield entry.kind, entry.content, entry.meta, f"{segment['name']}:{entry.seq}"
    for segment in found:
        carried = (segment.get("header") or {}).get("open_calls")
        for call, meta in (carried if isinstance(carried, dict) else {}).items():
            open_.setdefault(call, {"meta": meta, "where": "(carried):-1"})
        open_, more = audit(rows(segment), open_)
        findings.extend(more)
    return open_, marked, findings


def faults(found: list) -> list:
    """The findings of `audit` over every segment `gateway_ledger.check` returned."""
    return _walk(found)[2]


def scan(found: list, running: bool) -> dict:
    """{call id: row} for every started entry with no end entry in `gateway_ledger.check`'s
    result. A row has segment, seq, meta and `state`: "unsettled" when a gateway named the
    call (at a start, or when it was abandoned) or no gateway is running, else "open" (in
    flight, or not yet recorded)."""
    open_, marked, _findings = _walk(found)
    out = {}
    for call, row in open_.items():
        segment, _, seq = row["where"].rpartition(":")
        out[call] = {"segment": segment, "seq": int(seq), "meta": row["meta"],
                     "state": "unsettled" if (call in marked or not running) else "open"}
    return out
