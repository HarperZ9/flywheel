"""governance_envelope.py -- cross-lane governance state carrier.

Parallel to context_envelope.py (which carries index-lane catalog state into a
run), this carries governance state: TADR tier, control compliance, pause
triggers, authorization references, and risk signals. Every model boots knowing
the tier and its constraints.

Schema: flywheel.governance-envelope/v1.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

SCHEMA = "flywheel.governance-envelope/v1"
GOVERNANCE_VERDICTS = frozenset({"allow", "pause", "deny"})


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class GovernanceEnvelope:
    """Cross-lane governance state carried into every run.

    This envelope is produced once (from a TADR classification + control
    compliance check) and consumed by every lane that needs to know the tier,
    its constraints, and the authorization state.
    """
    tier: str = "T1"
    modifiers: list[str] = field(default_factory=list)
    control_compliance: dict[str, Any] = field(default_factory=dict)
    pause_triggers: list[str] = field(default_factory=list)
    authorization_receipt_ref: str = ""
    risk_signals: list[dict[str, Any]] = field(default_factory=list)
    classification_ref: str = ""  # seal_hash of the TADR classification receipt
    governance_verdict: str = "pause"  # allow / pause / deny
    timestamp: str = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        from .governance.tadr_tier import validate_modifiers, validate_tier

        if not validate_tier(self.tier):
            raise ValueError(f"invalid tier: {self.tier!r}")
        invalid = validate_modifiers(self.modifiers)
        if invalid:
            raise ValueError(f"invalid modifiers: {invalid}")
        if self.governance_verdict not in GOVERNANCE_VERDICTS:
            raise ValueError(
                f"invalid governance_verdict: {self.governance_verdict!r}")
        if not isinstance(self.control_compliance, dict):
            raise ValueError("control_compliance must be an object")
        if not isinstance(self.risk_signals, list) or not all(
                isinstance(item, dict) for item in self.risk_signals):
            raise ValueError("risk_signals must be a list of objects")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "tier": self.tier,
            "modifiers": list(self.modifiers),
            "control_compliance": dict(self.control_compliance),
            "pause_triggers": list(self.pause_triggers),
            "authorization_receipt_ref": self.authorization_receipt_ref,
            "risk_signals": list(self.risk_signals),
            "classification_ref": self.classification_ref,
            "governance_verdict": self.governance_verdict,
            "timestamp": self.timestamp,
            "fingerprint": self.fingerprint(),
        }

    def fingerprint(self) -> str:
        """Content-addressed fingerprint of the governance state."""
        body = {
            "tier": self.tier,
            "modifiers": list(self.modifiers),
            "control_compliance": self.control_compliance,
            "pause_triggers": list(self.pause_triggers),
            "authorization_receipt_ref": self.authorization_receipt_ref,
            "risk_signals": list(self.risk_signals),
            "classification_ref": self.classification_ref,
            "governance_verdict": self.governance_verdict,
            "timestamp": self.timestamp,
        }
        return _sha256_hex(
            json.dumps(body, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False).encode("utf-8"))[:16]

    def allows_action(self, action_tier: str) -> bool:
        """Check whether this envelope permits an action at the given tier.

        Uses the no-inflation rule: a T1 envelope cannot permit T3 actions.
        Also checks the governance_verdict: a paused or denied envelope blocks.
        """
        if self.governance_verdict == "deny":
            return False
        if self.governance_verdict == "pause":
            return False
        if not _complete_compliance(self.control_compliance):
            return False
        if not _nonzero_digest(self.classification_ref):
            return False
        # Inline tier rank check (avoids hard dependency on governance package)
        tier_ranks = {"T1": 1, "T2": 2, "T3": 3}
        env_rank = tier_ranks.get(self.tier)
        action_rank = tier_ranks.get(action_tier)
        if env_rank is None or action_rank is None:
            return False
        return action_rank <= env_rank


def _nonzero_digest(value: Any) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and value == value.lower() and value != "0" * 64
            and all(char in "0123456789abcdef" for char in value))


def _complete_compliance(report: dict[str, Any]) -> bool:
    keys = ("required", "measured", "present", "absent", "unknown")
    if not all(isinstance(report.get(key), int)
               and not isinstance(report.get(key), bool)
               and report[key] >= 0 for key in keys):
        return False
    derived = (report["present"] + report["absent"] + report["unknown"]
               == report["required"]
               and report["measured"] == report["present"] + report["absent"])
    complete = (derived and report["required"] > 0
                and report["present"] == report["required"]
                and report["absent"] == 0 and report["unknown"] == 0)
    return complete and report.get("compliant") is True


def build_envelope(
    *,
    tier: str = "T1",
    modifiers: list[str] | None = None,
    compliance_report: dict[str, Any] | None = None,
    classification_ref: str = "",
    authorization_receipt_ref: str = "",
    pause_triggers: list[str] | None = None,
) -> GovernanceEnvelope:
    """Build a governance envelope from a classification + compliance check.

    The verdict is 'allow' when controls are compliant, 'pause' when
    non-compliant but not denied, 'deny' when the tier is T3 and controls
    are critically missing.
    """
    modifiers = list(modifiers or [])
    pause_triggers = list(pause_triggers or [])
    compliance = compliance_report or {}

    absent = compliance.get("absent", 0)
    if (isinstance(absent, int) and not isinstance(absent, bool)
            and absent > 0 and tier == "T3"):
        verdict = "deny"
    elif (_complete_compliance(compliance)
          and _nonzero_digest(classification_ref) and not pause_triggers):
        verdict = "allow"
    else:
        verdict = "pause"

    return GovernanceEnvelope(
        tier=tier,
        modifiers=modifiers,
        control_compliance=compliance,
        pause_triggers=pause_triggers,
        authorization_receipt_ref=authorization_receipt_ref,
        classification_ref=classification_ref,
        governance_verdict=verdict,
    )
