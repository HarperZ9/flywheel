"""The scope block on a buildc byte-witness packet: what the bridge checked.

The list is positive: each entry names a step the bridge ran. A step that is
absent did not run. `inconclusive` is true when `buildc receipt verify` ran out
of time (exit 124 from run_buildc_verify): the verifier neither passed nor
failed the receipt, and the packet must not read as either.
"""
from __future__ import annotations

from typing import Any

TIMEOUT_EXIT = 124


def scope_block(fields: dict[str, Any], command_result: CommandResult | None,
                export_present: bool) -> dict[str, Any]:
    """What the bridge checked, in positive terms, and whether it is inconclusive."""
    checked = ["receipt_bytes_hashed"]
    if export_present:
        checked.append("export_bytes_hashed")
    if fields.get("source_digest"):
        checked.append("source_digest_read_from_receipt")
    if command_result is not None:
        checked.append("buildc_receipt_verify_ran")
        if command_result.exit_code == 0:
            checked.append("buildc_receipt_verify_exit_zero")
    return {"checked": checked,
            "inconclusive": command_result is not None
            and command_result.exit_code == TIMEOUT_EXIT}
