"""control_baseline.py -- TADR control baselines as checkable specs.

T1 requires 14 baseline controls. T2 adds 18 more. T3 adds 20 more. This
module defines each control as a checkable item and provides a compliance
checker that evaluates a run's configuration against its required tier.

The control IDs follow the pattern "tadr:T1:<slug>" etc., matching the
TADR manual sections 7-9.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# T1 minimum control baseline (section 7).
T1_CONTROLS = (
    ("named-owner", "Named accountable owner"),
    ("authorized-purpose", "Documented authorized purpose"),
    ("asset-inventory", "Asset and access inventory"),
    ("rbac", "Basic role-based access control"),
    ("change-approval", "Change approval"),
    ("safety-training", "Safety and security training"),
    ("operational-logging", "Operational logging"),
    ("tested-backup", "Tested backup or restoration"),
    ("incident-contact", "Incident contact path"),
    ("periodic-review", "Periodic review"),
    ("supplier-records", "Supplier records"),
    ("lawful-retention", "Lawful retention and disposal"),
    ("documented-exceptions", "Documented exceptions"),
    ("reporting-channel", "Means to report concerns without retaliation"),
)

# T2 enhanced controls (section 8, in addition to T1).
T2_CONTROLS = (
    ("separation-of-duties", "Separation of duties"),
    ("multi-party-auth", "Multi-party authorization for consequential changes"),
    ("pam", "Privileged-access management"),
    ("continuous-monitoring", "Continuous or high-frequency monitoring"),
    ("tamper-evident-logs", "Tamper-evident logs"),
    ("independent-testing", "Independent security or safety testing"),
    ("misuse-scenarios", "Explicit misuse and failure scenarios"),
    ("supplier-due-diligence", "Supplier due diligence and contingency"),
    ("rehearsed-incident-response", "Rehearsed incident response"),
    ("evidence-preservation", "Evidence-preservation procedures"),
    ("notification-criteria", "Stakeholder and regulator notification criteria"),
    ("rto-rpo", "Recovery-time and recovery-point objectives"),
    ("controlled-exceptions", "Controlled exception process with expiration"),
    ("insider-risk-controls", "Insider-risk controls"),
    ("red-team", "Red-team exercises within safety boundary"),
    ("leading-indicators", "Measurable leading indicators"),
    ("review-after-change", "Review after capability or deployment changes"),
    ("rights-assessment", "Legal, ethical, and human-rights assessment"),
)

# T3 catastrophic-risk controls (section 9, in addition to T1+T2).
T3_CONTROLS = (
    ("restricted-release", "Presumption against unrestricted public release"),
    ("catastrophic-risk-case", "Written catastrophic-risk case before operation"),
    ("external-review", "Independent external review"),
    ("compartmentalization", "Compartmentalization"),
    ("no-single-person-bypass", "No single-person ability to bypass safeguards"),
    ("dual-control-hazardous", "Dual control for hazardous actions"),
    ("continuous-pathway-monitoring", "Continuous monitoring of critical pathways"),
    ("replicated-evidence", "Secure, append-only, independently replicated evidence"),
    ("hardened-protection", "Hardened protection of code, weights, designs"),
    ("personnel-screening", "Supplier and personnel screening"),
    ("predefined-shutdown", "Predefined pause, isolation, rollback, shutdown"),
    ("emergency-intervention", "Tested emergency intervention under degraded conditions"),
    ("continuous-threat-intel", "Continuous threat intelligence"),
    ("adversarial-evaluation", "Adversarial evaluation for misuse and evasion"),
    ("documented-uncertainty", "Documented uncertainty and unresolved evidence"),
    ("executive-risk-acceptance", "Executive and board-level residual risk acceptance"),
    ("regulator-coordination", "Regulator or competent-authority coordination"),
    ("international-coordination", "International coordination where cross-border"),
    ("protected-dissent", "Protected internal dissent and non-retaliation"),
    ("post-incident-accounting", "Post-incident public accounting"),
)

# Combined tier -> controls mapping.
TIER_CONTROLS: dict[str, tuple] = {
    "T1": T1_CONTROLS,
    "T2": T1_CONTROLS + T2_CONTROLS,
    "T3": T1_CONTROLS + T2_CONTROLS + T3_CONTROLS,
}

CONTROL_TIERS = {
    **{slug: "T1" for slug, _ in T1_CONTROLS},
    **{slug: "T2" for slug, _ in T2_CONTROLS},
    **{slug: "T3" for slug, _ in T3_CONTROLS},
}
OBSERVATION_STATES = frozenset({"present", "absent", "unknown"})


@dataclass(frozen=True)
class ControlObservation:
    """One evidence-bearing observation of a required control."""
    control_id: str
    state: str
    source_ref: str
    observed_at: str
    checker_id: str

    def __post_init__(self) -> None:
        if self.state not in OBSERVATION_STATES:
            raise ValueError(f"invalid control state: {self.state!r}")
        if self.state != "unknown":
            for name in ("source_ref", "observed_at", "checker_id"):
                if not getattr(self, name):
                    raise ValueError(f"{name} is required for measured controls")

    def to_dict(self) -> dict[str, str]:
        return {
            "control_id": self.control_id, "state": self.state,
            "source_ref": self.source_ref, "observed_at": self.observed_at,
            "checker_id": self.checker_id,
        }


@dataclass
class ControlCheck:
    """The result of checking one control."""
    control_id: str
    name: str
    tier: str
    observation: ControlObservation

    def to_dict(self) -> dict[str, Any]:
        return {
            "control_id": self.observation.control_id, "name": self.name,
            "required_tier": self.tier,
            "observation": self.observation.to_dict(),
        }


@dataclass
class ComplianceReport:
    """The result of checking a run against its tier's control baseline."""
    tier: str
    required: int = 0
    measured: int = 0
    present: int = 0
    absent: int = 0
    unknown: int = 0
    checks: list[ControlCheck] = field(default_factory=list)

    @property
    def compliant(self) -> bool:
        return (self.required > 0 and self.measured == self.required
                and self.present == self.required and self.absent == 0
                and self.unknown == 0)

    @property
    def checked(self) -> int:
        """Compatibility alias for the v1 report surface."""
        return self.required

    @property
    def passed(self) -> int:
        """Compatibility alias for the v1 report surface."""
        return self.present

    @property
    def failed(self) -> int:
        """Compatibility alias; unknown evidence remains non-passing."""
        return self.absent + self.unknown

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier, "required": self.required,
            "measured": self.measured, "present": self.present,
            "absent": self.absent, "unknown": self.unknown,
            "checked": self.checked, "passed": self.passed,
            "failed": self.failed,
            "compliant": self.compliant,
            "checks": [c.to_dict() for c in self.checks],
        }


def check_compliance(
    tier: str,
    *,
    observations: list[ControlObservation | dict[str, str]] | None = None,
    **legacy_facts: Any,
) -> ComplianceReport:
    """Check whether a run meets its tier's control baseline.

    Omitted observations are unknown. Boolean legacy facts are rejected because
    they cannot identify their evidence source, observation time, or checker.
    """
    if tier not in TIER_CONTROLS:
        raise ValueError(f"invalid tier: {tier!r}")
    if legacy_facts:
        raise ValueError("boolean control facts are unsupported; provide observations")
    controls = TIER_CONTROLS[tier]
    supplied: dict[str, ControlObservation] = {}
    for raw in observations or []:
        observation = raw if isinstance(raw, ControlObservation) else ControlObservation(**raw)
        if observation.control_id in supplied:
            raise ValueError(f"duplicate control_id: {observation.control_id!r}")
        supplied[observation.control_id] = observation
    required_ids = {
        f"tadr:{CONTROL_TIERS[slug]}:{slug}" for slug, _ in controls}
    unknown_ids = sorted(set(supplied) - required_ids)
    if unknown_ids:
        raise ValueError(f"invalid control_id for {tier}: {unknown_ids}")
    report = ComplianceReport(tier=tier, required=len(controls))

    for control_id, name in controls:
        full_id = f"tadr:{CONTROL_TIERS[control_id]}:{control_id}"
        observation = supplied.get(full_id, ControlObservation(
            control_id=full_id, state="unknown", source_ref="unobserved",
            observed_at="", checker_id="flywheel.control-baseline/v1"))
        check = ControlCheck(
            control_id=control_id, name=name, tier=CONTROL_TIERS[control_id],
            observation=observation,
        )
        report.checks.append(check)
        if observation.state != "unknown":
            report.measured += 1
        if observation.state == "present":
            report.present += 1
        elif observation.state == "absent":
            report.absent += 1
        else:
            report.unknown += 1

    return report
