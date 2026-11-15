"""gateway_call_audit.py -- the call records of a gateway ledger, read from its entries.

  audit      the rules a call record keeps, checked from the entries alone:
             only an end entry closes a call, and an end with no start, a
             second end, a repeated start and an end that differs from its
             start on the route, the request or the caller are findings.
             `flywheel gateway-ledger verify` and the tests' `recorded` helper
             both call it, so the tool and the tests cannot disagree.
  faults     `audit` over every segment `gateway_ledger.check` returned.
  scan       the calls with a started entry and no end entry, with their
             state: unsettled, or open in a running gateway.

Until 2.0.0's sixth review round `verify` checked the chain of hashes and
named starts without ends. A ledger that showed a served call with no start
passed it; only a test helper held the other rules.
"""
from __future__ import annotations

from .gateway_calls import ENDS, GAP, MARKER, SAME, STARTED


def audit(rows, carried=None) -> tuple:
    """(open, findings) for entries in ledger order.

    `rows` yields (kind, content, meta, where). `open` maps the call id of each
    started entry with no end entry to {"meta", "where"}. A finding is
    (code, call, where, text); the codes are `malformed_start`,
    `repeated_start`, `end_without_start`, `second_end` and
    `end_differs_from_start`. One second end is the gateway's own: the `late` end of a
    call whose first end a `ledger_gap` entry names as unconfirmed (it reached the disk,
    its append reported a failure, and the reply was held back)."""
    open_, ended, findings, unconfirmed = dict(carried or {}), {}, [], set()
    for kind, content, meta, where in rows:
        meta = meta if isinstance(meta, dict) else {}
        call = meta.get("call")
        if kind == GAP:                 # entries on disk whose append reported a failure
            unconfirmed.update(f"{row.get('segment')}:{row.get('seq')}" for row in (
                meta.get("unconfirmed") or []) if isinstance(row, dict))
        elif kind == STARTED:
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
                if again and meta.get("late") is True and ended[call] in unconfirmed:
                    continue            # the reply recorded there was held back: its last word
                findings.append(("second_end" if again else "end_without_start", str(call),
                                 where, f"{kind} for a call that already has an end entry"
                                 if again else f"{kind} with no started entry before it"))
                continue
            ended[call] = where
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
