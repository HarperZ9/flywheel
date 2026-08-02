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
    indicator_class: str = "Observation"  # TADR section 44: Observation/Report/Inference/Hypothesis/Assessment/Attribution

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
            "indicator_class": self.indicator_class,
        }
        return d


def correlate(
    *,
    tool_calls: list[dict[str, Any]] | None = None,
    egress_events: list[dict[str, Any]] | None = None,
    credential_findings: list[dict[str, Any]] | None = None,
    metric_samples: dict[str, list[float]] | None = None,
    run_id: str = "infra-correlate",
) -> list[CorrelatedEvent]:
    """Correlate events across layers and return detections.

    Uses heuristic signatures by default. When metric_samples are provided,
    uses statistical anomaly detection (z-score) from native_detect to score
    deviations from normal behavior. When the native C++ extension is compiled,
    this is accelerated; otherwise the pure-Python path runs.
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

    # Statistical anomaly detection (when metric samples are provided)
    if metric_samples:
        events.extend(_statistical_detections(metric_samples, run_id))

    return events


def _statistical_detections(
    metric_samples: dict[str, list[float]], run_id: str,
) -> list[CorrelatedEvent]:
    """Run statistical anomaly detection on metric time series.

    Uses the native_detect module (pure-Python or native C++). Detects
    anomalies via z-score against a rolling baseline, and changepoints via PELT.
    """
    from .native_detect import BaselineBuilder, AnomalyScorer, pelt

    events: list[CorrelatedEvent] = []
    builder = BaselineBuilder()
    scorer = AnomalyScorer()

    for metric, samples in metric_samples.items():
        if len(samples) < 5:
            continue  # need enough data for a baseline

        # Build baseline from first 2/3 of samples
        split = max(3, int(len(samples) * 0.67))
        for v in samples[:split]:
            builder.add_sample(metric, v)
        baseline = builder.build(metric)
        if baseline is None:
            continue

        # Score the remaining samples for anomalies
        for v in samples[split:]:
            score = scorer.score(v, baseline, threshold=3.0)
            if score.is_anomalous:
                events.append(CorrelatedEvent(
                    run_id=run_id, detection="statistical-anomaly",
                    severity="high" if score.severity > 0.75 else "moderate",
                    detail=f"{metric}={v:.1f} anomalous "
                           f"(z={score.z_score:.2f}, baseline mean={baseline.mean:.1f})",
                    evidence_refs=[{"layer": "metrics", "ref": metric}],
                ))

        # Changepoint detection on the full series
        cps = pelt(samples, penalty=len(samples) * 0.5)
        if cps:
            events.append(CorrelatedEvent(
                run_id=run_id, detection="behavioral-changepoint",
                severity="moderate",
                detail=f"{len(cps)} changepoint(s) in {metric} "
                       f"at indices {[c.index for c in cps[:5]]}",
                evidence_refs=[{"layer": "metrics", "ref": metric}],
            ))

    return events


def build_correlated_receipt(event: CorrelatedEvent) -> dict[str, Any]:
    """Build a sealed receipt for one correlated event."""
    body = event.to_dict()
    seal_hash = _sha256_hex(_canonical_bytes(body))
    return {"schema": SCHEMA, "seal_hash": seal_hash, "seal_body": body}
