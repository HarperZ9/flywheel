"""tool_witness.py -- every tool call leaves the bytes it moved behind.

A call moves two byte sequences: the arguments in, and the output back. Both
are witnessed onto one chain per run, so what a stranger rechecks is the whole
ordered run rather than one receipt at a time. A call inserted after the fact
has to forge every link that follows it.

The bytes are encoded the way the receipt encodes them, so the digest in the
receipt and the digest in the chain are the same digest. The two records bind
by construction, with nothing to keep in step by hand, and a test pins the
equality so a change to either encoding fails loudly instead of quietly
splitting the record in two.

The chain runs whether or not receipts are being written. A receipt directory
is something a caller opts into. The chain is what the run did.

Nothing here raises. A call that fails to be witnessed is still a call, and
breaking the tool path to protect the record would trade the work for the
paperwork.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .action_witness import INPUT, OUTPUT, observe, open_log

RECEIPT_JSON = "receipt-json"
REPR = "repr"
UTF8 = "utf-8"


def open_chain(run_id: Any, directory: Any = None):
    """The run's action chain, or None when it cannot be opened.

    A run with no name has no chain. That is a caller's mistake and not a
    reason to stop the run, so it is reported by the absence of a chain rather
    than by an exception out of the tool path.
    """
    try:
        return open_log(str(run_id),
                        directory=Path(directory) if directory else None)
    except Exception:
        return None


def receipt_args_bytes(args: Any) -> tuple[bytes, str]:
    """The argument bytes a tool-call receipt hashes, and how they were made.

    This mirrors ``build_receipt``'s encoding deliberately, empty-args rule
    included, so the receipt's digest and the chain's digest are one digest.
    Arguments no encoder will take still get witnessed, under a name that says
    which rule produced them, because an action missing from the chain is worse
    than an action whose bytes came from a weaker rule.
    """
    if not args:
        return b"", RECEIPT_JSON
    try:
        return json.dumps(args, sort_keys=True,
                          ensure_ascii=False).encode(UTF8), RECEIPT_JSON
    except (TypeError, ValueError):
        return repr(args).encode(UTF8), REPR


def witness_call(log, *, tool: str, args: Any, output: str, ok: bool, seq: int,
                 capability: str = "", outcome: str = "") -> dict | None:
    """Witness one call's two byte sequences. Never raises.

    Returns what binds the call to the chain, or None when there was no chain
    to witness onto.
    """
    if log is None:
        return None
    try:
        payload, encoding = receipt_args_bytes(args)
        context = {"capability": capability, "outcome": outcome, "ok": bool(ok)}
        action = f"tool:{tool}"
        first = observe(log, payload, action=action, kind=INPUT, seq=seq,
                        encoding=encoding, context=context)
        second = observe(log, (output or "").encode(UTF8), action=action,
                         kind=OUTPUT, seq=seq, encoding=UTF8, context=context)
        return {"args_sha256": first.sha256, "output_sha256": second.sha256,
                "bytes": first.length + second.length, "link": second.link()}
    except Exception:
        return None


def seal_call(receipt_dir: Any, *, tool: str, capability: str, admission: str,
              args: Any, output: str, ok: bool, outcome: str, run_id: str,
              seq: int, prev: str, rationale: dict | None = None) -> str:
    """Write one sealed receipt and return the new chain head. Never raises.

    A receipt that was built but could not be written still advances the head,
    so the next receipt points back at a receipt the directory does not hold
    and the chain reads as broken rather than as complete. That is the same
    rule the action log follows, and for the same reason: a hole that still
    reads as a clean run is the failure neither layer can afford.

    A receipt that could not be built leaves the head where it was, because
    there is no record for anything to point at.
    """
    from .tool_call_receipt import (_canonical_bytes, _sha256_hex, build_receipt,
                                    emit_receipt)
    try:
        receipt = build_receipt(
            tool=tool, capability=capability, admission=admission, args=args,
            output=output, ok=ok, rc=0 if ok else 1, run_id=run_id, seq=seq,
            prev_receipt_sha256=prev, outcome=outcome, rationale=rationale)
        emit_receipt(receipt, Path(receipt_dir))
        probe = dict(receipt)
        probe["seal"] = {"algorithm": "sha256", "hex": ""}
        return _sha256_hex(_canonical_bytes(probe))
    except Exception:
        return prev
