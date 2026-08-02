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


@dataclass
class ControlCheck:
    """The result of checking one control."""
    control_id: str
    name: str
    tier: str
    present: bool = False
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "control_id": f"tadr:{self.tier}:{self.control_id}",
            "name": self.name, "present": self.present, "detail": self.detail,
        }


@dataclass
class ComplianceReport:
    """The result of checking a run against its tier's control baseline."""
    tier: str
    checked: int = 0
    passed: int = 0
    failed: int = 0
    checks: list[ControlCheck] = field(default_factory=list)

    @property
    def compliant(self) -> bool:
        return self.failed == 0 and self.checked > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier, "checked": self.checked,
            "passed": self.passed, "failed": self.failed,
            "compliant": self.compliant,
            "checks": [c.to_dict() for c in self.checks],
        }


def check_compliance(
    tier: str,
    *,
    has_named_owner: bool = True,
    has_operational_logging: bool = True,
    has_tested_backup: bool = True,
    has_rbac: bool = True,
    has_change_approval: bool = True,
    has_tamper_evident_logs: bool = False,
    has_multi_party_auth: bool = False,
    has_continuous_monitoring: bool = False,
    has_dual_control: bool = False,
    has_external_review: bool = False,
    has_emergency_shutdown: bool = False,
    has_restricted_release: bool = False,
    has_independent_testing: bool = False,
    **kwargs: Any,
) -> ComplianceReport:
    """Check whether a run meets its tier's control baseline.

    This is a heuristic checker: it maps configuration facts to TADR control
    IDs and reports which are present or missing. A missing control at the
    required tier is a compliance failure.
    """
    controls = TIER_CONTROLS.get(tier, T1_CONTROLS)
    report = ComplianceReport(tier=tier)

    # Map configuration facts to control IDs.
    fact_map: dict[str, bool] = {
        "named-owner": has_named_owner,
        "rbac": has_rbac,
        "change-approval": has_change_approval,
        "operational-logging": has_operational_logging,
        "tested-backup": has_tested_backup,
        "tamper-evident-logs": has_tamper_evident_logs,
        "multi-party-auth": has_multi_party_auth,
        "continuous-monitoring": has_continuous_monitoring,
        "dual-control-hazardous": has_dual_control,
        "external-review": has_external_review,
        "emergency-intervention": has_emergency_shutdown,
    }

    for control_id, name in controls:
        present = fact_map.get(control_id, False)
        check = ControlCheck(
            control_id=control_id, name=name,
            tier=tier, present=present,
            detail="present" if present else "missing",
        )
        report.checks.append(check)
        report.checked += 1
        if present:
            report.passed += 1
        else:
            report.failed += 1

    return report
