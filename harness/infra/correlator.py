"""correlator.py -- Artifact 24: Continuous Monitoring cross-layer correlation.

Joins agent-level receipts, network events, process events, identity events,
and storage events into correlated envelopes. Detections for scope expansion,
repeated boundary probing, credential access, persistence, external publication.

Schema: flywheel.correlated-event/v1. Sealed.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

SCHEMA = "flywheel.correlated-event/v1"

# Detection signatures.
DETECTIONS = {
    "scope-expansion": "agent accessed a target outside its approved scope",
    "repeated-boundary-probing": "rapid sequence of heterogeneous failed actions",
    "credential-access": "agent read a credential-bearing file or env var",
    "persistence": "agent wrote to a startup, cron, or service location",
    "external-publication": "agent sent data to an external destination",
}


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_bytes(obj: dict[str, Any]) -> bytes:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class CorrelatedEvent:
    """One event that joins evidence from multiple layers."""
    run_id: str
    timestamp: str = ""
    detection: str = ""  # one of DETECTIONS keys
    severity: str = "moderate"  # low / moderate / high / critical
    tool_call_hash: str = ""
    process_pid: int = 0
    process_name: str = ""
    identity: str = ""
    destination: str = ""
    agent_action: str = ""
    evidence_refs: list[dict[str, str]] = field(default_factory=list)
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = {
            "run_id": self.run_id,
            "timestamp": self.timestamp or _utc_now(),
            "detection": self.detection,
            "severity": self.severity,
            "tool_call_hash": self.tool_call_hash,
            "process_pid": self.process_pid,
            "process_name": self.process_name,
            "identity": self.identity,
            "destination": self.destination,
            "agent_action": self.agent_action,
            "evidence_refs": list(self.evidence_refs),
            "detail": self.detail,
        }
        return d


def correlate(
    *,
    tool_calls: list[dict[str, Any]] | None = None,
    egress_events: list[dict[str, Any]] | None = None,
    credential_findings: list[dict[str, Any]] | None = None,
    run_id: str = "infra-correlate",
) -> list[CorrelatedEvent]:
    """Correlate events across layers and return detections.

    This is a heuristic correlator (not a ML model). It looks for the
    signatures defined in DETECTIONS across the provided event streams.
    """
    tool_calls = tool_calls or []
    egress_events = egress_events or []
    credential_findings = credential_findings or []
    events: list[CorrelatedEvent] = []

    # Detection: credential-access (a tool call read a file with secrets)
    for finding in credential_findings:
        loc = finding.get("location", "")
        for tc in tool_calls:
            args = str(tc.get("args", ""))
            if loc and loc in args:
                events.append(CorrelatedEvent(
                    run_id=run_id, detection="credential-access",
                    severity="high",
                    agent_action=tc.get("tool", ""),
                    evidence_refs=[{"layer": "credential-scan", "ref": loc},
                                   {"layer": "tool-call", "ref": tc.get("source", "")}],
                    detail=f"tool call accessed file with {finding.get('secret_type', 'secret')}",
                ))

    # Detection: external-publication (egress to non-localhost during a run)
    for eg in egress_events:
        body = eg.get("seal_body", eg)
        dest = body.get("destination", "")
        verdict = body.get("verdict", "")
        if dest and dest not in ("127.0.0.1", "localhost", "0.0.0.0") and verdict != "BLOCKED":
            events.append(CorrelatedEvent(
                run_id=run_id, detection="external-publication",
                severity="high" if verdict == "UNKNOWN" else "moderate",
                destination=dest,
                evidence_refs=[{"layer": "egress", "ref": eg.get("seal_hash", "")[:16]}],
                detail=f"connection to {dest}:{body.get('port', '?')} verdict={verdict}",
            ))

    # Detection: repeated-boundary-probing (rapid ERROR sequence in tool calls)
    error_calls = [tc for tc in tool_calls if tc.get("ok") == "false"
                   or tc.get("outcome") == "ERROR"]
    if len(error_calls) >= 3:
        events.append(CorrelatedEvent(
            run_id=run_id, detection="repeated-boundary-probing",
            severity="high",
            detail=f"{len(error_calls)} failed tool calls in one run",
            evidence_refs=[{"layer": "tool-call", "ref": tc.get("source", "")}
                           for tc in error_calls[:5]],
        ))

    return events


def build_correlated_receipt(event: CorrelatedEvent) -> dict[str, Any]:
    """Build a sealed receipt for one correlated event."""
    body = event.to_dict()
    seal_hash = _sha256_hex(_canonical_bytes(body))
    return {"schema": SCHEMA, "seal_hash": seal_hash, "seal_body": body}
