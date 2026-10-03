"""adopt.py -- the two places Flywheel calls the shared checks.

Search: CheckedOracle wraps the selector. A candidate whose checks do not all
pass is rejected before the selector's own test run, and its receipts are kept
for the search stage.

Pre-action monitor: monitor_layer0 builds the monitor's layer-0 callable from
per-tool rules. A tool call whose arguments fail a check is blocked, with the
check's code and receipt digest in the reason.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..oracle import OracleResult
from . import PASS, CheckReceipt, run_all, worst
from .receipt import digest


class CheckedOracle:
    """Run the checks on each candidate before `base`; any non-PASS rejects it."""

    def __init__(self, base, checks: list[tuple[str, dict]]):
        self.base, self.checks = base, list(checks)
        self.oracle_type = getattr(base, "oracle_type", "checked")
        self.receipts: dict[str, list[CheckReceipt]] = {}

    def verify(self, candidate: str, task) -> OracleResult:
        receipts = run_all(candidate, self.checks)
        self.receipts[_text_key(candidate)] = receipts
        if worst(receipts) == PASS:
            return self.base.verify(candidate, task)
        bad = [r for r in receipts if r.verdict != PASS]
        excerpt = "; ".join(f"{r.check}:{r.code}" for r in bad)
        return OracleResult(passed=False, cmd=f"checks[{len(self.checks)}]",
                            output_hash=digest([r.to_dict() for r in receipts]),
                            stdout_excerpt=excerpt[:500], rc=1)

    def receipts_for(self, candidate: str) -> list[dict]:
        return [r.to_dict() for r in self.receipts.get(_text_key(candidate), [])]


def _text_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def monitor_layer0(rules: dict, inner=None):
    """rules: {tool: [{"check": kind, "spec": {...}, "arg": name-or-null}]}.

    Returns callable(call, ctx) -> reason or None, for Monitor(layer0=...).
    `inner`, an existing layer-0 callable, runs first and keeps its reason.
    """
    def layer0(call, ctx):
        if inner is not None:
            reason = inner(call, ctx)
            if reason:
                return reason
        for rule in rules.get(call.tool, []):
            subject = call.args if rule.get("arg") is None else call.args.get(rule["arg"])
            receipts = run_all(subject, [(rule["check"], rule.get("spec", {}))])
            if worst(receipts) != PASS:
                r = receipts[0]
                return (f"check {r.check} {r.verdict} ({r.code}): {r.reason}; "
                        f"receipt sha256 {digest(r.to_dict())[:16]}")
        return None
    return layer0


def load_rules(path) -> dict:
    """Read monitor check rules from a JSON file shaped like monitor_layer0 expects."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: check rules must be a JSON object keyed by tool name")
    return data
