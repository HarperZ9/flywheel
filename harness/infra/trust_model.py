"""trust_model.py -- Artifact 16: System Architecture and Trust Model.

A machine-readable architecture model that marks which concrete component
enforces each policy, the owner/version/config/deployment for every component,
single-point-of-failure analysis, and adversary/accidental-failure paths.

The ARCHIVE QUERY acceptance test: for every safety claim, the diagram
identifies a concrete enforcement component and an accountable owner.

Schema: flywheel.trust-model/v1. Not sealed (it is a declared model, not a
witnessed event), but validated structurally: every safety claim must name an
enforcement component and an owner.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SCHEMA = "flywheel.trust-model/v1"

COMPONENT_TYPES = frozenset({
    "model", "harness", "tool", "gate", "monitor", "identity-provider",
    "network", "container", "storage", "stop-mechanism", "observer", "other",
})


@dataclass
class Component:
    """One component in the architecture, with its enforcement role."""
    name: str
    component_type: str
    owner: str
    version: str = ""
    config_ref: str = ""
    deployment: str = ""
    enforces: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "component_type": self.component_type,
            "owner": self.owner,
            "version": self.version,
            "config_ref": self.config_ref,
            "deployment": self.deployment,
            "enforces": list(self.enforces),
            "notes": self.notes,
        }


@dataclass
class SafetyClaim:
    """A safety claim that must be backed by a concrete enforcement component."""
    claim_id: str
    statement: str
    enforcement_component: str
    owner: str
    failure_mode: str = ""
    confidence: str = "moderate"

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "statement": self.statement,
            "enforcement_component": self.enforcement_component,
            "owner": self.owner,
            "failure_mode": self.failure_mode,
            "confidence": self.confidence,
        }


@dataclass
class TrustModel:
    """The full architecture trust model."""
    model_id: str
    components: list[Component] = field(default_factory=list)
    safety_claims: list[SafetyClaim] = field(default_factory=list)
    single_points_of_failure: list[str] = field(default_factory=list)
    adversary_paths: list[str] = field(default_factory=list)
    description: str = ""
    tadr_tier: str = ""
    tadr_modifiers: list[str] = field(default_factory=list)
    classification_ref: str = ""
    governance_verdict: str = ""
    pause_triggers: list[str] = field(default_factory=list)
    control_digest: str = ""

    def __post_init__(self) -> None:
        from harness.governance.tadr_tier import validate_modifiers, validate_tier

        if self.tadr_tier and not validate_tier(self.tadr_tier):
            raise ValueError(f"invalid tadr_tier: {self.tadr_tier!r}")
        invalid = validate_modifiers(self.tadr_modifiers)
        if invalid or (self.tadr_modifiers and not self.tadr_tier):
            raise ValueError(f"invalid tadr_modifiers: {invalid or self.tadr_modifiers}")
        if self.governance_verdict and self.governance_verdict not in {
                "allow", "pause", "deny"}:
            raise ValueError(f"invalid governance_verdict: {self.governance_verdict!r}")
        for name in ("classification_ref", "control_digest"):
            value = getattr(self, name)
            if value and not _nonzero_digest(value):
                raise ValueError(f"invalid {name}")

    def add_component(self, **kwargs: Any) -> Component:
        comp = Component(**kwargs)
        if comp.component_type not in COMPONENT_TYPES:
            raise ValueError(f"component_type {comp.component_type!r} not valid")
        self.components.append(comp)
        return comp

    def add_claim(self, **kwargs: Any) -> SafetyClaim:
        claim = SafetyClaim(**kwargs)
        self.safety_claims.append(claim)
        return claim

    def to_dict(self) -> dict[str, Any]:
        # Validate TADR tier if set (fail-closed on invalid values)
        if self.tadr_tier:
            from harness.governance.tadr_tier import validate_tier
            if not validate_tier(self.tadr_tier):
                raise ValueError(f"invalid tadr_tier: {self.tadr_tier!r}")
        result = {
            "schema": SCHEMA,
            "model_id": self.model_id,
            "description": self.description,
            "components": [c.to_dict() for c in self.components],
            "safety_claims": [c.to_dict() for c in self.safety_claims],
            "single_points_of_failure": list(self.single_points_of_failure),
            "adversary_paths": list(self.adversary_paths),
        }
        governance: dict[str, Any] = {}
        if self.tadr_tier:
            governance["tadr_tier"] = self.tadr_tier
        if self.tadr_modifiers:
            governance["tadr_modifiers"] = list(self.tadr_modifiers)
        if self.classification_ref:
            governance["classification_ref"] = self.classification_ref
        if self.governance_verdict:
            governance["governance_verdict"] = self.governance_verdict
        if self.pause_triggers:
            governance["pause_triggers"] = list(self.pause_triggers)
        if self.control_digest:
            governance["control_digest"] = self.control_digest
        if governance:
            result["governance"] = governance
        return result

    def validate(self) -> list[str]:
        """Validate the trust model. Returns a list of issues (empty = valid).

        The acceptance test: every safety claim must name an enforcement
        component that exists in the model, and every component type must be
        valid. Single points of failure are flagged but not errors.
        """
        issues: list[str] = []
        comp_names = {c.name for c in self.components}

        for claim in self.safety_claims:
            if not claim.enforcement_component:
                issues.append(
                    f"claim {claim.claim_id!r}: no enforcement_component named")
            elif claim.enforcement_component not in comp_names:
                issues.append(
                    f"claim {claim.claim_id!r}: enforcement_component "
                    f"{claim.enforcement_component!r} not in components")
            if not claim.owner:
                issues.append(f"claim {claim.claim_id!r}: no owner named")

        for comp in self.components:
            if comp.component_type not in COMPONENT_TYPES:
                issues.append(
                    f"component {comp.name!r}: type {comp.component_type!r} invalid")
            if not comp.owner:
                issues.append(f"component {comp.name!r}: no owner named")

        return issues

    def find_single_points_of_failure(self) -> list[str]:
        """Identify components that are the sole enforcer of any safety claim."""
        enforcers: dict[str, list[str]] = {}
        for claim in self.safety_claims:
            comp = claim.enforcement_component
            if comp:
                enforcers.setdefault(comp, []).append(claim.claim_id)
        return [comp for comp, claims in enforcers.items() if len(claims) > 0
                and sum(1 for c in self.components if c.name == comp) == 1]


def default_flywheel_trust_model() -> TrustModel:
    """A trust model capturing Flywheel's own architecture.

    This is the self-model: it names which Flywheel component enforces which
    safety property. It is honest about single points of failure.
    """
    from harness.infra.run_bom import installed_harness_version
    _v = installed_harness_version()
    model = TrustModel(
        model_id="flywheel-default",
        description="Flywheel's agent-layer accountability architecture.",
    )
    model.add_component(
        name="ToolGate", component_type="gate", owner="flywheel",
        version=_v, enforces=["default-deny-write", "default-deny-exec"],
        notes="The capability broker. Off by default for writes and exec.")
    model.add_component(
        name="ToolCallReceipt", component_type="monitor", owner="flywheel",
        version=_v, enforces=["every-tool-call-sealed"],
        notes="Sealed receipt at the execute() chokepoint.")
    model.add_component(
        name="CanaryTripwire", component_type="monitor", owner="flywheel",
        version=_v, enforces=["decoy-access-detected"],
        notes="Decoy resources that trip containment if accessed.")
    model.add_component(
        name="GatewayAuth", component_type="identity-provider", owner="flywheel",
        version=_v, enforces=["localhost-only", "bearer-token"],
        notes="Host allowlist defeats DNS rebinding. Token on state-changing methods.")
    model.add_component(
        name="LessonStore", component_type="storage", owner="flywheel",
        version=_v, enforces=["organizational-learning"],
        notes="Append-only, hash-chained lesson memory.")

    model.add_claim(
        claim_id="C1", statement="Writes are denied by default",
        enforcement_component="ToolGate", owner="flywheel",
        failure_mode="gate bypassed via shell",
        confidence="high")
    model.add_claim(
        claim_id="C2", statement="Every tool call is sealed and chain-linked",
        enforcement_component="ToolCallReceipt", owner="flywheel",
        failure_mode="receipt emission fails silently",
        confidence="high")
    model.add_claim(
        claim_id="C3", statement="Decoy resource access is detected",
        enforcement_component="CanaryTripwire", owner="flywheel",
        failure_mode="decoy not placed in the agent's reach",
        confidence="moderate")
    model.add_claim(
        claim_id="C4", statement="Gateway is localhost-only",
        enforcement_component="GatewayAuth", owner="flywheel",
        failure_mode="DNS rebinding from a malicious page",
        confidence="high")

    model.single_points_of_failure = model.find_single_points_of_failure()
    model.adversary_paths = [
        "model -> tool dispatch -> shell -> credential file",
        "model -> tool dispatch -> network egress (gap: no network monitor)",
        "model -> generated script -> cron -> persistence (gap: no process monitor)",
    ]
    return model


def _nonzero_digest(value: str) -> bool:
    return (len(value) == 64 and value == value.lower() and value != "0" * 64
            and all(char in "0123456789abcdef" for char in value))
