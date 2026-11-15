"""Stable process exit codes for canon command surfaces."""
from __future__ import annotations

EX_OK = 0
EX_GATE = 1
EX_USAGE = 2
EX_UNAVAILABLE = 3
EX_SECURITY = 4
EX_CONFLICT = 5
EX_BUDGET = 6
EX_UNSUPPORTED = 7
EX_IO = 8
EX_INTERNAL = 70

_FAILURE_EXIT_CODES = {
    "ok": EX_OK,
    "readiness_failed": EX_GATE,
    "source_changed": EX_GATE,
    "invalid_args": EX_USAGE,
    "source_unreachable": EX_UNAVAILABLE,
    "unsafe_path": EX_SECURITY,
    "secret_quarantine": EX_SECURITY,
    "conflict": EX_CONFLICT,
    "critical_atom_loss": EX_BUDGET,
    "tier_mislabeled": EX_UNSUPPORTED,
    "unsupported_lifecycle": EX_UNSUPPORTED,
    "io_error": EX_IO,
    "isolation_refused": EX_SECURITY,
    "store_invalid": EX_IO,
    "store_busy": EX_CONFLICT,
    "not_found": EX_USAGE,
    "budget_too_small": EX_BUDGET,
    "edits_pending": EX_CONFLICT,
    "undeclared_loss": EX_GATE,
    "unsupported_format": EX_UNSUPPORTED,
    "shadowed": EX_CONFLICT,
    "not_confirmed": EX_GATE,
    "plan_stale": EX_CONFLICT,
    "residue_found": EX_GATE,
    "scrub_incomplete": EX_GATE,
    "audit_failed": EX_GATE,
}


def exit_code_for(failure_code: str) -> int:
    """Return the stable process exit code for a canon failure code."""
    if not isinstance(failure_code, str):
        return EX_INTERNAL
    return _FAILURE_EXIT_CODES.get(failure_code, EX_INTERNAL)


__all__ = [
    "EX_OK",
    "EX_GATE",
    "EX_USAGE",
    "EX_UNAVAILABLE",
    "EX_SECURITY",
    "EX_CONFLICT",
    "EX_BUDGET",
    "EX_UNSUPPORTED",
    "EX_IO",
    "EX_INTERNAL",
    "exit_code_for",
]
