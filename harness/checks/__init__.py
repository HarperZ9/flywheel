"""harness.checks -- one library of deterministic checks, one call shape, one receipt.

    from harness.checks import run
    receipt = run("recompute", 125, {"expr": "a ^ b", "inputs": {"a": 74, "b": 51}})
    receipt.verdict   # "FAIL": 74 XOR 51 is 121

Kinds: schema, ast, fsm, value_on_page, recompute. Every check takes
(subject, spec) and returns a CheckReceipt with verdict PASS, FAIL or
UNVERIFIABLE. A check that raises is recorded as UNVERIFIABLE with code
check_error, never as PASS.
"""
from __future__ import annotations

import logging

from .evidence import recompute_check, value_on_page_check
from .receipt import FAIL, PASS, UNVERIFIABLE, CheckReceipt, digest
from .structural import ast_check, fsm_check, schema_check

log = logging.getLogger(__name__)

CHECKS = {
    "schema": schema_check,
    "ast": ast_check,
    "fsm": fsm_check,
    "value_on_page": value_on_page_check,
    "recompute": recompute_check,
}


def run(kind: str, subject, spec: dict | None = None) -> CheckReceipt:
    spec = spec or {}
    fn = CHECKS.get(kind)
    if fn is None:
        raise ValueError(f"unknown check {kind!r}; expected one of {sorted(CHECKS)}")
    try:
        verdict, code, reason = fn(subject, spec)
    except Exception as exc:  # recorded, not swallowed: the receipt carries it
        log.warning("check %s raised %s: %s", kind, type(exc).__name__, exc)
        verdict, code, reason = UNVERIFIABLE, "check_error", f"{type(exc).__name__}: {exc}"
    return CheckReceipt(check=kind, verdict=verdict, code=code, reason=reason,
                        subject_sha256=digest(subject), spec_sha256=digest(spec))


def run_all(subject, checks: list[tuple[str, dict]]) -> list[CheckReceipt]:
    """Run each (kind, spec) on one subject, in order."""
    return [run(kind, subject, spec) for kind, spec in checks]


def worst(receipts: list[CheckReceipt]) -> str:
    """FAIL beats UNVERIFIABLE beats PASS; no receipts is PASS."""
    verdicts = {r.verdict for r in receipts}
    return FAIL if FAIL in verdicts else UNVERIFIABLE if UNVERIFIABLE in verdicts else PASS


__all__ = ["CHECKS", "CheckReceipt", "FAIL", "PASS", "UNVERIFIABLE", "run", "run_all",
           "worst"]
