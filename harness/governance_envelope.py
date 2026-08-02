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
    governance_verdict: str = "allow"  # allow / pause / deny
    timestamp: str = field(default_factory=_utc_now)

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
            "tier": self.tier, "modifiers": sorted(self.modifiers),
            "pause_triggers": sorted(self.pause_triggers),
            "governance_verdict": self.governance_verdict,
            "classification_ref": self.classification_ref,
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
        # Inline tier rank check (avoids hard dependency on governance package)
        tier_ranks = {"T1": 1, "T2": 2, "T3": 3}
        env_rank = tier_ranks.get(self.tier, 0)
        action_rank = tier_ranks.get(action_tier, 0)
        return action_rank <= env_rank


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

    failed = compliance.get("failed", 0)
    tier_val = tier

    if failed > 0 and tier_val == "T3":
        verdict = "deny"
    elif failed > 0:
        verdict = "pause"
    else:
        verdict = "allow"

    return GovernanceEnvelope(
        tier=tier_val,
        modifiers=modifiers,
        control_compliance=compliance,
        pause_triggers=pause_triggers,
        authorization_receipt_ref=authorization_receipt_ref,
        classification_ref=classification_ref,
        governance_verdict=verdict,
    )
