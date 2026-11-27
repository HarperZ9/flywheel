# SPDX-License-Identifier: MIT
"""Superoptimizer V6 MIR rewrite chain verifier.

Verifies buildlang.superopt-cert/v1 certificates for monotone MIR cost
reduction (total_cost_after <= total_cost_before and per-step cost_after <=
cost_before), rewrite step sum consistency, valid MIR SHA-256 digests, and
bounded floating-point ULP error witnesses.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .shader_cert import is_hex64

HONEST_SCOPE_LIMIT = (
    "Verifies buildlang.superopt-cert/v1 structural integrity, MIR SHA-256 "
    "formatting, step-level and total monotone cost (after <= before), step "
    "sum consistency, and bounded ULP witness ceilings. Does not re-run the "
    "e-graph or SMT equivalence prover."
)

SUPEROPT_CERT_SCHEMA = "buildlang.superopt-cert/v1"


@dataclass(frozen=True)
class SuperoptChainReport:
    """Fail-closed verification result for one superoptimizer certificate."""

    passed: bool
    target: str
    rewrites_applied: int
    total_cost_before: int
    total_cost_after: int
    cost_delta: int
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a deterministic JSON-serializable summary."""
        return {
            "passed": self.passed,
            "target": self.target,
            "rewrites_applied": self.rewrites_applied,
            "total_cost_before": self.total_cost_before,
            "total_cost_after": self.total_cost_after,
            "cost_delta": self.cost_delta,
            "reasons": list(self.reasons),
        }


def _is_nonneg_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def extract_superopt_cert(gpu_cert: Mapping[str, object]) -> Mapping[str, object] | None:
    """Return embedded superopt_cert mapping from a GPU cert, or None."""
    if not isinstance(gpu_cert, Mapping):
        return None
    inner = gpu_cert.get("superopt_cert")
    return inner if isinstance(inner, Mapping) else None


def _check_steps(
    steps: object,
    rewrites: int,
    raw_before: object,
    raw_after: object,
    max_allowed_ulps: int,
    reasons: list[str],
) -> None:
    if not isinstance(steps, list):
        reasons.append("INVALID_STEPS_LIST")
        return
    if len(steps) != rewrites:
        reasons.append(f"REWRITE_COUNT_MISMATCH:{len(steps)}!={rewrites}")
    sb_sum, sa_sum, valid_costs = 0, 0, True
    for idx, step in enumerate(steps):
        if not isinstance(step, Mapping):
            reasons.append(f"INVALID_STEP:{idx}")
            valid_costs = False
            continue
        rule = step.get("rule")
        if not isinstance(rule, str) or not rule.strip():
            reasons.append(f"STEP_MISSING_RULE:{idx}")
        sb, sa = step.get("cost_before"), step.get("cost_after")
        if not _is_nonneg_int(sb) or not _is_nonneg_int(sa):
            reasons.append(f"STEP_INVALID_COST:{idx}")
            valid_costs = False
        else:
            sb_sum += int(sb)
            sa_sum += int(sa)
            if int(sa) > int(sb):
                reasons.append(f"STEP_COST_REGRESSION:{idx}:{sb}->{sa}")
        witness = step.get("error_witness")
        if isinstance(witness, Mapping) and "max_ulps" in witness:
            ulps = witness["max_ulps"]
            if not _is_nonneg_int(ulps) or int(ulps) > max_allowed_ulps:
                reasons.append(f"STEP_ULP_EXCEEDS_BOUND:{idx}:{ulps}")
    if valid_costs and _is_nonneg_int(raw_before) and _is_nonneg_int(raw_after):
        if sb_sum != int(raw_before) or sa_sum != int(raw_after):
            reasons.append(f"STEP_COST_SUM_MISMATCH:{sb_sum}/{sa_sum}!={raw_before}/{raw_after}")


def verify_superopt_cert(
    cert: Mapping[str, object],
    *,
    expected_target: str | None = None,
    max_allowed_ulps: int = 1,
) -> SuperoptChainReport:
    """Verify one buildlang.superopt-cert/v1 certificate fail-closed."""
    if not isinstance(cert, Mapping):
        return SuperoptChainReport(False, "", 0, 0, 0, 0, ("INVALID_SUPEROPT_OBJECT",))
    reasons: list[str] = []
    target = str(cert.get("target", ""))
    if cert.get("schema") != SUPEROPT_CERT_SCHEMA:
        reasons.append("INVALID_SUPEROPT_SCHEMA")
    if expected_target is not None and target != expected_target:
        reasons.append(f"SUPEROPT_TARGET_MISMATCH:{target}!={expected_target}")
    if cert.get("verified") is not True:
        reasons.append("SUPEROPT_NOT_VERIFIED")
    for field, code in (
        ("mir_before_sha256", "MALFORMED_MIR_BEFORE_SHA256"),
        ("mir_after_sha256", "MALFORMED_MIR_AFTER_SHA256"),
        ("cert_sha256", "MALFORMED_SUPEROPT_CERT_SHA256"),
    ):
        if not is_hex64(cert.get(field)):
            reasons.append(code)
    raw_before, raw_after, raw_rewrites = cert.get("total_cost_before"), cert.get("total_cost_after"), cert.get("rewrites_applied")
    if not _is_nonneg_int(raw_before) or not _is_nonneg_int(raw_after):
        reasons.append("INVALID_TOTAL_COST")
        total_before, total_after = 0, 0
    else:
        total_before, total_after = int(raw_before), int(raw_after)
        if total_after > total_before:
            reasons.append(f"TOTAL_COST_REGRESSION:{total_before}->{total_after}")
    if not _is_nonneg_int(raw_rewrites):
        reasons.append("INVALID_REWRITES_COUNT")
        rewrites = 0
    else:
        rewrites = int(raw_rewrites)
    _check_steps(cert.get("steps"), rewrites, raw_before, raw_after, max_allowed_ulps, reasons)
    return SuperoptChainReport(not reasons, target, rewrites, total_before, total_after, total_before - total_after, tuple(reasons))
