"""local_tools_receipt.py -- seal one tool-call receipt for a ToolExecutor call.

Split out of local_tools.py so that module stays under its file-gate count.
Witnesses the bytes a call moved, then seals a receipt over them. The witness
runs whether or not receipts are being written, because the chain is what the
run did and the receipt directory is opt-in; both hash the same argument bytes,
so the two records name one digest. When the pre-action monitor held or blocked
the call, admission is ESCALATED and outcome BLOCKED: the call never ran.
"""
from __future__ import annotations


def emit_tool_receipt(ex, name, args, result, rationale=None, preaction=None) -> None:
    if not ex._receipt_run_id:
        return
    from .tool_witness import seal_call, witness_call
    cap, admission, witness_meta = ex._classify_capability(name)
    if preaction is not None and preaction.get("verdict") in ("HOLD", "BLOCK"):
        admission, outcome = "ESCALATED", "BLOCKED"
    else:
        outcome = ("COMPLETED" if result.ok
                   else ("BLOCKED" if result.output.startswith("[gate]") else "ERROR"))
    ex._receipt_seq += 1
    witness_call(ex._action_log, tool=name, args=args, output=result.output,
                 ok=result.ok, seq=ex._receipt_seq, capability=cap,
                 outcome=outcome, context=witness_meta)
    if not ex.receipt_dir:
        return
    ex._receipt_prev_sha256 = seal_call(
        ex.receipt_dir, tool=name, capability=cap, admission=admission,
        args=args, output=result.output, ok=result.ok, outcome=outcome,
        run_id=ex._receipt_run_id, seq=ex._receipt_seq,
        prev=ex._receipt_prev_sha256, rationale=rationale, preaction=preaction)
