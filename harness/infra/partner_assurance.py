"""partner_assurance.py -- Artifact 23: Third-Party Evaluation Assurance Package.

Defines the joint threat model, exchanged configuration baselines, independently
tested internet paths, telemetry ownership, escalation thresholds, and stop
authority per party. Emits flywheel.partner-assurance/v1 receipt when both
parties confirm the same network state.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

SCHEMA = "flywheel.partner-assurance/v1"


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_bytes(obj: dict[str, Any]) -> bytes:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


@dataclass
class PartnerAssurancePackage:
    """The assurance package for a third-party evaluation partnership."""
    package_id: str
    parties: list[str] = field(default_factory=list)  # ["OpenAI", "Irregular"]
    threat_model: str = ""
    config_baselines_exchanged: bool = False
    internet_paths_tested: bool = False
    identity_boundaries_tested: bool = False
    telemetry_ownership: dict[str, str] = field(default_factory=dict)  # layer -> owner
    escalation_thresholds: dict[str, str] = field(default_factory=dict)
    stop_authority_per_party: dict[str, bool] = field(default_factory=dict)
    network_state_confirmed: dict[str, bool] = field(default_factory=dict)  # party -> confirmed
    rapid_disclosure_agreed: bool = False
    notes: str = ""

    def confirm_network_state(self, party: str) -> None:
        """A party confirms the network state matches the agreed baseline."""
        self.network_state_confirmed[party] = True

    def all_confirmed(self) -> bool:
        """True when all parties have confirmed the network state."""
        return (len(self.network_state_confirmed) >= len(self.parties)
                and all(self.network_state_confirmed.values()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "package_id": self.package_id,
            "parties": list(self.parties),
            "threat_model": self.threat_model,
            "config_baselines_exchanged": self.config_baselines_exchanged,
            "internet_paths_tested": self.internet_paths_tested,
            "identity_boundaries_tested": self.identity_boundaries_tested,
            "telemetry_ownership": dict(self.telemetry_ownership),
            "escalation_thresholds": dict(self.escalation_thresholds),
            "stop_authority_per_party": dict(self.stop_authority_per_party),
            "network_state_confirmed": dict(self.network_state_confirmed),
            "rapid_disclosure_agreed": self.rapid_disclosure_agreed,
            "all_confirmed": self.all_confirmed(),
            "notes": self.notes,
        }

    def sealed(self) -> dict[str, Any]:
        d = self.to_dict()
        body = {k: v for k, v in d.items() if k not in ("schema",)}
        d["seal_hash"] = _sha256_hex(_canonical_bytes(body))
        return d


def default_package(parties: list[str]) -> PartnerAssurancePackage:
    """Create a default partner assurance package for the given parties."""
    pkg = PartnerAssurancePackage(
        package_id=f"PA-{hashlib.sha256(str(parties).encode()).hexdigest()[:12]}",
        parties=list(parties),
        threat_model="agentic evaluation with potential for real-world reach",
        telemetry_ownership={
            "agent-actions": parties[0] if parties else "",
            "network-flows": parties[1] if len(parties) > 1 else "",
            "identity-events": "shared",
        },
        escalation_thresholds={
            "boundary-crossing": "immediate-stop",
            "credential-access": "notify-within-1h",
            "external-publication": "notify-within-24h",
        },
        stop_authority_per_party={p: True for p in parties},
        rapid_disclosure_agreed=True,
    )
    return pkg
