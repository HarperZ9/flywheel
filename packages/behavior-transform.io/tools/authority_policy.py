"""Rule-based policy engine for authority enforcement.

Sits between environment resolution and gate enforcement. Policies
express compound requirements, rate limits, and cooldown windows
that flat entitlement checks cannot.

Policy rules are evaluated in order. A deny from any rule is final.
An allow requires all rules to pass.

Built-in policies:
  - compound_entitlement: entitlement A requires B to also be present
  - rate_limit: no more than N checks of entitlement X per window
  - cooldown: minimum interval between consecutive checks of X
  - session_required: entitlement X requires an active session
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from env_authority import AuthorityGrant


SCHEMA = "behavior-transform.authority-policy.v1"


@dataclass(frozen=True)
class PolicyVerdict:
    """Result of evaluating a policy rule set."""
    allowed: bool
    entitlement: str
    rules_evaluated: int
    rules_passed: int
    denial_rule: str = ""
    denial_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "entitlement": self.entitlement,
            "rules_evaluated": self.rules_evaluated,
            "rules_passed": self.rules_passed,
            "denial_rule": self.denial_rule,
            "denial_reason": self.denial_reason,
        }


@dataclass(frozen=True)
class PolicyRule:
    """Single policy rule."""
    name: str
    rule_type: str
    entitlement: str
    config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "rule_type": self.rule_type,
            "entitlement": self.entitlement,
            "config": self.config,
        }


_check_timestamps: dict[str, list[float]] = {}


def _prune_timestamps(key: str, window: float) -> None:
    cutoff = time.time() - window
    if key in _check_timestamps:
        _check_timestamps[key] = [
            t for t in _check_timestamps[key] if t > cutoff
        ]


def record_check(entitlement: str, surface: str = "") -> None:
    """Record a timestamp for rate limit and cooldown tracking."""
    key = f"{surface}:{entitlement}" if surface else entitlement
    _check_timestamps.setdefault(key, []).append(time.time())


def clear_check_history() -> None:
    """Clear all recorded timestamps."""
    _check_timestamps.clear()


def _eval_compound(
    rule: PolicyRule,
    grant: AuthorityGrant,
    entitlement: str,
) -> tuple[bool, str]:
    required = rule.config.get("requires", [])
    for req in required:
        if req not in grant.entitlements:
            return False, f"compound: {entitlement} requires {req}"
    return True, ""


def _eval_rate_limit(
    rule: PolicyRule,
    grant: AuthorityGrant,
    entitlement: str,
) -> tuple[bool, str]:
    max_count = rule.config.get("max_count", 60)
    window = rule.config.get("window_seconds", 60)
    key = f"{grant.surface}:{entitlement}" if grant else entitlement
    _prune_timestamps(key, window)
    count = len(_check_timestamps.get(key, []))
    if count >= max_count:
        return False, f"rate_limit: {count}/{max_count} in {window}s window"
    return True, ""


def _eval_cooldown(
    rule: PolicyRule,
    grant: AuthorityGrant,
    entitlement: str,
) -> tuple[bool, str]:
    min_interval = rule.config.get("min_interval_seconds", 1)
    key = f"{grant.surface}:{entitlement}" if grant else entitlement
    timestamps = _check_timestamps.get(key, [])
    if timestamps:
        elapsed = time.time() - timestamps[-1]
        if elapsed < min_interval:
            return False, f"cooldown: {elapsed:.1f}s < {min_interval}s minimum"
    return True, ""


def _eval_session_required(
    rule: PolicyRule,
    grant: AuthorityGrant,
    entitlement: str,
) -> tuple[bool, str]:
    try:
        from session_authority import list_sessions
        active = list_sessions(active_only=True, surface=grant.surface)
        if not active:
            return False, "session_required: no active session"
    except ImportError:
        return False, "session_required: session_authority not available"
    return True, ""


_EVALUATORS = {
    "compound_entitlement": _eval_compound,
    "rate_limit": _eval_rate_limit,
    "cooldown": _eval_cooldown,
    "session_required": _eval_session_required,
}


DEFAULT_POLICIES: list[PolicyRule] = [
    PolicyRule(
        name="inoculate_requires_transform",
        rule_type="compound_entitlement",
        entitlement="inoculate",
        config={"requires": ["transform"]},
    ),
    PolicyRule(
        name="condition_requires_transform",
        rule_type="compound_entitlement",
        entitlement="condition",
        config={"requires": ["transform"]},
    ),
    PolicyRule(
        name="seal_requires_transform",
        rule_type="compound_entitlement",
        entitlement="seal",
        config={"requires": ["transform"]},
    ),
    PolicyRule(
        name="infer_rate_limit",
        rule_type="rate_limit",
        entitlement="infer",
        config={"max_count": 120, "window_seconds": 60},
    ),
]


class PolicyEngine:
    """Evaluates policy rules against grants and entitlements."""

    def __init__(self, rules: list[PolicyRule] | None = None) -> None:
        self._rules = rules if rules is not None else list(DEFAULT_POLICIES)

    @property
    def rules(self) -> list[PolicyRule]:
        return list(self._rules)

    def add_rule(self, rule: PolicyRule) -> None:
        self._rules.append(rule)

    def evaluate(
        self,
        entitlement: str,
        grant: AuthorityGrant,
    ) -> PolicyVerdict:
        """Evaluate all applicable rules for an entitlement."""
        applicable = [
            r for r in self._rules
            if r.entitlement == entitlement or r.entitlement == "*"
        ]

        if not applicable:
            return PolicyVerdict(
                allowed=True,
                entitlement=entitlement,
                rules_evaluated=0,
                rules_passed=0,
            )

        passed = 0
        for rule in applicable:
            evaluator = _EVALUATORS.get(rule.rule_type)
            if evaluator is None:
                continue

            ok, reason = evaluator(rule, grant, entitlement)
            if not ok:
                return PolicyVerdict(
                    allowed=False,
                    entitlement=entitlement,
                    rules_evaluated=len(applicable),
                    rules_passed=passed,
                    denial_rule=rule.name,
                    denial_reason=reason,
                )
            passed += 1

        return PolicyVerdict(
            allowed=True,
            entitlement=entitlement,
            rules_evaluated=len(applicable),
            rules_passed=passed,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "rules": [r.to_dict() for r in self._rules],
        }


_engine: PolicyEngine | None = None


def policy_engine(rules: list[PolicyRule] | None = None) -> PolicyEngine:
    """Get the singleton policy engine."""
    global _engine
    if _engine is None:
        _engine = PolicyEngine(rules)
    return _engine


def evaluate_policy(
    entitlement: str,
    grant: AuthorityGrant,
) -> PolicyVerdict:
    """Evaluate policy for an entitlement against a grant."""
    return policy_engine().evaluate(entitlement, grant)
