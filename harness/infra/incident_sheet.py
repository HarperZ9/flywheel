"""incident_sheet.py -- Artifact 14: Incident Identity Sheet.

Generates a stable incident identity from a correlated event. Incident ID,
detection time, commander, affected organizations, system class, severity,
status, jurisdictions. Links to related-but-distinct events without merging.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

SCHEMA = "flywheel.incident-sheet/v1"

STATUSES = ("detected", "investigating", "contained", "resolved", "closed")
SEVERITIES = ("low", "moderate", "high", "critical")
COMMAND_ROLES = frozenset({
    "incident_commander", "records_custodian", "legal_counsel",
    "technical_lead", "communications_lead", "safety_lead",
    "security_lead", "executive_sponsor", "regulator_liaison",
})


@dataclass
class IncidentSheet:
    """One incident identity, stable across teams and workflows."""
    incident_id: str
    detection_time: str
    incident_commander: str = ""
    records_custodian: str = ""
    affected_organizations: list[str] = field(default_factory=list)
    system_class: str = ""  # "agent-eval", "production", "research", etc.
    severity: str = "moderate"
    status: str = "detected"
    jurisdictions: list[str] = field(default_factory=list)
    related_incidents: list[str] = field(default_factory=list)
    root_correlated_event: str = ""  # seal_hash of the triggering event
    first_harmful_action: str = ""
    containment_time: str = ""
    notification_time: str = ""
    closure_time: str = ""
    notes: str = ""
    tadr_tier: str = ""  # TADR consequence tier (separate from operational severity)
    command_roles: dict[str, str] = field(default_factory=dict)  # role_name -> person
    classification_ref: str = ""

    def __post_init__(self) -> None:
        from harness.governance.tadr_tier import validate_tier

        if self.tadr_tier and not validate_tier(self.tadr_tier):
            raise ValueError(f"invalid tadr_tier: {self.tadr_tier!r}")
        if self.classification_ref and not _nonzero_digest(self.classification_ref):
            raise ValueError("invalid classification_ref")
        invalid_roles = sorted(set(self.command_roles) - COMMAND_ROLES)
        if invalid_roles or not all(
                isinstance(value, str) and value for value in self.command_roles.values()):
            raise ValueError(f"invalid command role names or values: {invalid_roles}")

    def to_dict(self) -> dict[str, Any]:
        if self.command_roles:
            invalid_roles = sorted(set(self.command_roles) - COMMAND_ROLES)
            if invalid_roles:
                raise ValueError(f"invalid command role(s): {invalid_roles}")
        result = {
            "schema": SCHEMA,
            "incident_id": self.incident_id,
            "detection_time": self.detection_time,
            "incident_commander": self.incident_commander,
            "records_custodian": self.records_custodian,
            "affected_organizations": list(self.affected_organizations),
            "system_class": self.system_class,
            "severity": self.severity,
            "status": self.status,
            "jurisdictions": list(self.jurisdictions),
            "related_incidents": list(self.related_incidents),
            "root_correlated_event": self.root_correlated_event,
            "first_harmful_action": self.first_harmful_action,
            "containment_time": self.containment_time,
            "notification_time": self.notification_time,
            "closure_time": self.closure_time,
            "notes": self.notes,
        }
        if self.tadr_tier:
            result["tadr_tier"] = self.tadr_tier
        if self.classification_ref:
            result["classification_ref"] = self.classification_ref
        if self.command_roles:
            result["command_roles"] = dict(self.command_roles)
        return result

    def link_related(self, other_id: str) -> None:
        """Link a related incident without merging."""
        if other_id != self.incident_id and other_id not in self.related_incidents:
            self.related_incidents.append(other_id)

    def set_status(self, status: str) -> None:
        if status not in STATUSES:
            raise ValueError(f"status {status!r} not in {STATUSES}")
        self.status = status


def from_correlated_event(event: dict[str, Any], *,
                          commander: str = "") -> IncidentSheet:
    """Generate an incident sheet from a correlated event receipt."""
    body = event.get("seal_body", event)
    severity = body.get("severity", "moderate")
    if severity not in SEVERITIES:
        severity = "moderate"
    return IncidentSheet(
        incident_id=f"INC-{uuid.uuid4().hex[:12]}",
        detection_time=body.get("timestamp", datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ")),
        incident_commander=commander,
        root_correlated_event=event.get("seal_hash", ""),
        severity=severity,
        system_class=body.get("run_id", ""),
        notes=body.get("detail", body.get("detection", "")),
        tadr_tier=body.get("tadr_tier", ""),
        classification_ref=body.get("classification_ref", ""),
    )


def _nonzero_digest(value: str) -> bool:
    return (len(value) == 64 and value == value.lower() and value != "0" * 64
            and all(char in "0123456789abcdef" for char in value))
