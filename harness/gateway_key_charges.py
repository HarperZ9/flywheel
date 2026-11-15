"""gateway_key_charges.py -- a gateway key is charged for one call once.

A key's totals are a running sum in `gateway-keys.json`. Until 2.0.0's sixth
review round nothing tied a debit to the call it was for, so the same call
could be charged twice:

  - a gateway killed after the debit and before the call's end entry left the
    key charged and the call unsettled, and the operator who then settled it
    with the provider's figures charged it again;
  - `settle` debited and then appended its entry, so a settle that stopped
    between the two charged again when it was repeated;
  - two requests that arrived together each applied one settle request.

Now every debit of a call carries the call id, and the key's row keeps the
ids of the calls it was last charged for with what each was charged, written
in the same file write as the totals:

  seen(row, call)    the tokens `call` was charged, or None
  note(row, call, n) record it. The row keeps the newest calls only: KEPT of
                     them, or twice the key's in-flight limit when that is
                     more. A gateway that is killed leaves at most the
                     in-flight limit of charged calls without an end entry.

`Keys.debit` skips a call it has seen. The record is short on purpose, so it
is not the only memory: a gateway that finds an unsettled call at its start
writes what the key was already charged for it into the ledger's
`calls_unsettled` entry (gateway_calls.Calls.announce), while the record
still holds it. `settle` reads both.

The row is not tamper-evident (docs/KNOWN-LIMITS-2.0.0.md, issue #490): a
process that can rewrite the key list can also rewrite this record.
"""
from __future__ import annotations

FIELD = "charged_calls"
KEPT = 32                               # per key; eight times the default in-flight limit


def seen(row: dict, call: str) -> "int | None":
    """What `call` was charged to this key, or None when the row does not hold it."""
    if not call:
        return None
    for pair in reversed(row.get(FIELD) or []):
        if isinstance(pair, list) and len(pair) == 2 and pair[0] == call:
            return int(pair[1])
    return None


def note(row: dict, call: str, spent: int) -> None:
    if call:
        limit = row.get("in_flight")
        kept = max(KEPT, 2 * limit if type(limit) is int else 0)
        row[FIELD] = ([pair for pair in (row.get(FIELD) or []) if isinstance(pair, list)]
                      + [[call, int(spent)]])[-kept:]


def before(home, open_calls: dict) -> dict:
    """{call: tokens} for the open calls of `open_calls` their keys were already charged for."""
    from . import gateway_key_gate
    out, rows = {}, None
    for call, meta in open_calls.items():
        if not isinstance(meta, dict) or "key_fp" not in meta:
            continue
        if rows is None:
            rows = gateway_key_gate.open_keys(home).rows()
        row = rows.get(meta.get("key"))
        if row is not None and row.get("fingerprint") == meta["key_fp"]:
            charged = seen(row, call)
            if charged is not None:
                out[call] = charged
    return out
