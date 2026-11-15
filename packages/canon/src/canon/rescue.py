from __future__ import annotations

from .adapter import descriptor_for, validate_adapter_descriptor
from .atom import CanonAtom
from .canonical_json import canonical_json_text, sha256_text
from .capsule import Budget, CapsuleCompileRequest, CapsuleTarget, SourceState
from .schema import Record


class RescueError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def build_rescue_request(
    *,
    records: tuple[Record, ...],
    atoms: tuple[CanonAtom, ...],
    target: str,
    source_state: SourceState,
    budget: Budget,
    profile: str = "handoff",
) -> CapsuleCompileRequest:
    descriptor = _descriptor(target)
    capsule_target = CapsuleTarget(descriptor.adapter_id, "CANON.md", descriptor.integration_tier, False)
    return CapsuleCompileRequest(
        profile=profile,
        target=capsule_target,
        source_state=source_state,
        budget=budget,
        atoms=atoms,
        records=records,
        does_not_prove=_does_not_prove(descriptor),
        required_atom_ids=_critical_atom_ids(atoms),
        readiness_probe_id=_probe_id(capsule_target, source_state, profile),
        readiness_target=_readiness_target(descriptor, capsule_target),
    )


def _descriptor(target_id: object):
    if type(target_id) is not str:
        raise RescueError("invalid_args")
    try:
        descriptor = descriptor_for(target_id)
    except KeyError as exc:
        raise RescueError("invalid_args") from exc
    if validate_adapter_descriptor(descriptor) or "CANON.md" not in descriptor.target_surfaces:
        raise RescueError("invalid_args")
    if descriptor.integration_tier == "unsupported":
        raise RescueError("unsupported_lifecycle")
    return descriptor


def _critical_atom_ids(atoms: tuple[CanonAtom, ...]) -> tuple[str, ...]:
    return tuple(atom.id for atom in atoms if atom.critical is True)


def _does_not_prove(descriptor: object) -> tuple[str, ...]:
    return tuple(descriptor.known_unknowns) + (  # type: ignore[attr-defined]
        "This compile does not prove readiness acknowledgement or host-level enforcement.",
    )


def _probe_id(target: CapsuleTarget, source_state: SourceState, profile: str) -> str:
    payload = {"profile": profile, "source_state": source_state.to_dict(), "target": target.to_dict()}
    return "probe-" + sha256_text(canonical_json_text(payload)).removeprefix("sha256:")[:16]


def _readiness_target(descriptor: object, target: CapsuleTarget) -> dict[str, object]:
    return {
        "adapter": target.adapter,
        "bootstrap": descriptor.bootstrap,  # type: ignore[attr-defined]
        "host_enforcement_observed": target.host_enforcement_observed,
        "integration_tier": target.integration_tier,
        "known_unknowns": list(descriptor.known_unknowns),  # type: ignore[attr-defined]
        "surface": target.surface,
    }


__all__ = ["RescueError", "build_rescue_request"]
