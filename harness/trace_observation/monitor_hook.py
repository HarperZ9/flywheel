"""monitor_hook.py -- turn a flagged trajectory into a hold in the pre-action monitor.

Flags come only from measured findings this package produces, never from a
model's say-so:

- measured-gap documentation drift (a run contradicted the provider's
  documented exposure, so every claim built on that documentation is suspect);
- a failed false-success control (the instrument itself is broken);
- an observation-gap verdict whose interval excludes zero (behavior differed
  between observed and unobserved cue arms on this run's families);
- a finding an owner-configured component submits through Finding.

Each finding is written as an observation receipt into the monitor chain
first; the hold is then armed with that receipt's seal, so a reviewer can walk
from the held call to the evidence. If the receipt cannot be written, no flag
is raised and the error propagates (fail closed, as the monitor does).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..preaction import trace_flag
from .channel import A0, NONE
from .receipt import ObservationLedger, build_receipt, utc_now

FINDING_DOES_NOT_PROVE = (
    "A finding is a measured result on this run's records. It does not show intent; "
    "the task, instructions and environment explain the behavior.")


@dataclass
class Finding:
    rule_id: str
    basis: str                     # what the finding rests on, for the reviewer
    evidence: dict = field(default_factory=dict)
    channel: str = NONE
    access_class: str = A0


def findings_from_measured_gap(gap_record: dict) -> list:
    drift = gap_record.get("documentation_drift") or []
    if not drift:
        return []
    return [Finding("trace/documentation-drift", "measured-gap",
                    {"provider": gap_record.get("provider", ""), "fields": list(drift)})]


def findings_from_controls(component: str, controls: list) -> list:
    failed = [c["control_id"] for c in controls if c.get("passed") != "true"]
    if not failed:
        return []
    return [Finding("trace/control-failed", "false-success control bank",
                    {"component": component, "failed": failed})]


def findings_from_observation(result: dict) -> list:
    """result is behavioral.observation.analyze() output."""
    flagged = [p for p, g in (result.get("gaps") or {}).items()
               if g.get("status") == "ok" and g.get("excludes_zero") == "true"]
    if not flagged:
        return []
    return [Finding("trace/observation-gap", "observed-versus-unobserved arms",
                    {"pairs": flagged, "ois": result.get("ois", "")})]


def raise_holds(home, run_id: str, findings: list, *, subject: dict,
                raised_at: str = "") -> list:
    """Receipt first, then the flag. Returns one entry per finding."""
    ledger = ObservationLedger(home)
    raised_at = raised_at or utc_now()
    out = []
    for f in findings:
        receipt = build_receipt(
            run_id=run_id, component=f"flag:{f.rule_id}", subject=subject,
            inputs={"basis": f.basis}, result={"verdict": "FLAGGED", "evidence": _strings(f.evidence)},
            gaps=[], does_not_prove=FINDING_DOES_NOT_PROVE,
            started_utc=raised_at, finished_utc=raised_at)
        seal = ledger.append(receipt)
        flag = trace_flag.raise_trace_flag(
            home, run_id=run_id, rule_id=f.rule_id, channel=f.channel,
            access_class=f.access_class,
            evidence_sha256=trace_flag.evidence_digest([f.rule_id, _strings(f.evidence)]),
            raised_at=raised_at, observation_receipt_sha256=seal)
        out.append({"rule_id": f.rule_id, "receipt_sha256": seal, **flag})
    return out


def _strings(value):
    if isinstance(value, dict):
        return {str(k): _strings(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_strings(v) for v in value]
    return value if isinstance(value, str) else str(value)
