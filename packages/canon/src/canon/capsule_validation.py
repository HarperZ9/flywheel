from __future__ import annotations

from typing import Callable

from .adapter import INTEGRATION_TIERS
from .atom import CanonAtom, validate_atom
from .canonical_json import CanonicalJSONError, is_sha256_ref
from .capsule_rules import (
    atom_sort_key,
    atoms_of_type,
    duplicate_atom_identities,
    freshness,
    layers,
    safe_atom_sort_key,
    sorted_omissions,
    sorted_receipts,
    sorted_records,
    sorted_transforms,
)
from .capsule_types import (
    CANONICALIZATION,
    CAPSULE_PROFILES,
    CAPSULE_SCHEMA,
    SOURCE_STATE_DIGEST_KEYS,
    Budget,
    Capsule,
    CapsuleTarget,
    Compatibility,
    Integrity,
    SourceState,
    capsule_digest,
)
from .omission import Omission, validate_omission
from .schema import SCHEMA as RECORD_SCHEMA, Record
from .transform import TransformReceipt, validate_transform_receipt
from .validator import validate_record


def validate_capsule(capsule: Capsule) -> list[str]:
    if not isinstance(capsule, Capsule):
        return ["capsule must be a Capsule"]
    problems: list[str] = []
    _check_member("profile", capsule.profile, CAPSULE_PROFILES, problems)
    _check_sha256("capsule_id", capsule.capsule_id, problems)
    _check_target(capsule.target, problems)
    _check_source_state(capsule.source_state, problems)
    _check_compatibility(capsule.compatibility, problems)
    _check_budget(capsule.profile, capsule.budget, problems)
    _check_string_tuple("layers", capsule.layers, problems)
    _check_nested("atoms", capsule.atoms, CanonAtom, validate_atom, problems)
    for key in duplicate_atom_identities(capsule.atoms):
        problems.append(f"atoms contain duplicate atom identity {key!r}")
    _check_nested("records", capsule.records, Record, validate_record, problems)
    _check_nested("conflicts", capsule.conflicts, CanonAtom, validate_atom, problems)
    _check_nested("unknowns", capsule.unknowns, CanonAtom, validate_atom, problems)
    _check_nested("omissions", capsule.omissions, Omission, validate_omission, problems)
    _check_nested("lossy_transforms", capsule.lossy_transforms, TransformReceipt, validate_transform_receipt, problems)
    _check_dict_tuple("freshness", capsule.freshness, problems)
    _check_dict_tuple("receipts", capsule.receipts, problems)
    _check_string_tuple("does_not_prove", capsule.does_not_prove, problems)
    _check_integrity(capsule, problems)
    _check_ordering(capsule, problems)
    _check_derived_fields(capsule, problems)
    return problems


def _check_member(name: str, value: object, allowed: tuple[str, ...], problems: list[str]) -> None:
    if value not in allowed:
        problems.append(f"{name} must be one of {list(allowed)}, got {value!r}")


def _check_non_empty_string(name: str, value: object, problems: list[str]) -> None:
    if not isinstance(value, str) or value == "":
        problems.append(f"{name} must be a non-empty string")


def _check_sha256(name: str, value: object, problems: list[str]) -> None:
    if not is_sha256_ref(value):
        problems.append(f"{name} must be a sha256: reference")


def _check_non_negative_int(name: str, value: object, problems: list[str]) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        problems.append(f"{name} must be a non-negative int")


def _check_string_tuple(name: str, value: object, problems: list[str]) -> None:
    if not isinstance(value, tuple):
        problems.append(f"{name} must be a tuple")
        return
    for position, item in enumerate(value):
        if not isinstance(item, str):
            problems.append(f"{name}[{position}] must be a string")


def _check_dict_tuple(name: str, value: object, problems: list[str]) -> None:
    if not isinstance(value, tuple):
        problems.append(f"{name} must be a tuple")
        return
    for position, item in enumerate(value):
        if not isinstance(item, dict):
            problems.append(f"{name}[{position}] must be a dict")


def _check_nested(name: str, value: object, item_type: type, validator: Callable[[object], list[str]], problems: list[str]) -> None:
    if not isinstance(value, tuple):
        problems.append(f"{name} must be a tuple")
        return
    for position, item in enumerate(value):
        if not isinstance(item, item_type):
            problems.append(f"{name}[{position}] must be a {item_type.__name__}")
            continue
        if isinstance(item, CanonAtom):
            _check_atom_identity_components(f"{name}[{position}]", item, problems)
        try:
            item_problems = validator(item)
        except (TypeError, ValueError, AttributeError) as exc:
            problems.append(f"{name}[{position}]: validation failed with {type(exc).__name__}: {exc}")
            continue
        for problem in item_problems:
            problems.append(f"{name}[{position}]: {problem}")


def _check_atom_identity_components(prefix: str, atom: CanonAtom, problems: list[str]) -> None:
    if isinstance(atom.precedence_rank, bool) or not isinstance(atom.precedence_rank, int):
        problems.append(f"{prefix}: precedence_rank must be a non-bool int")
    for name in ("scope_key", "layer", "type", "id"):
        value = getattr(atom, name)
        if not isinstance(value, str) or value == "":
            problems.append(f"{prefix}: {name} must be a non-empty string")


def _check_target(target: object, problems: list[str]) -> None:
    if not isinstance(target, CapsuleTarget):
        problems.append("target must be a CapsuleTarget")
        return
    _check_non_empty_string("target.adapter", target.adapter, problems)
    _check_non_empty_string("target.surface", target.surface, problems)
    _check_member("target.integration_tier", target.integration_tier, INTEGRATION_TIERS, problems)
    if not isinstance(target.host_enforcement_observed, bool):
        problems.append("target.host_enforcement_observed must be bool")
    if target.host_enforcement_observed is True and target.integration_tier != "enforced":
        problems.append("target.host_enforcement_observed requires integration_tier 'enforced'")


def _check_source_state(source_state: object, problems: list[str]) -> None:
    if not isinstance(source_state, SourceState):
        problems.append("source_state must be a SourceState")
        return
    for key in SOURCE_STATE_DIGEST_KEYS:
        value = getattr(source_state, key)
        if key == "records_digest" or value is not None:
            _check_sha256(f"source_state.{key}", value, problems)


def _check_compatibility(compatibility: object, problems: list[str]) -> None:
    if not isinstance(compatibility, Compatibility):
        problems.append("compatibility must be a Compatibility")
        return
    if compatibility.record_schema_min != RECORD_SCHEMA:
        problems.append(f"compatibility.record_schema_min must be {RECORD_SCHEMA!r}")
    if compatibility.capsule_schema != CAPSULE_SCHEMA:
        problems.append(f"compatibility.capsule_schema must be {CAPSULE_SCHEMA!r}")
    _check_string_tuple("compatibility.requires_features", compatibility.requires_features, problems)


def _check_budget(profile: str, budget: object, problems: list[str]) -> None:
    if not isinstance(budget, Budget):
        problems.append("budget must be a Budget")
        return
    _check_member("budget.profile", budget.profile, CAPSULE_PROFILES, problems)
    if budget.profile != profile:
        problems.append("budget.profile must match profile")
    _check_non_negative_int("budget.max_tokens", budget.max_tokens, problems)
    _check_non_negative_int("budget.estimated_tokens", budget.estimated_tokens, problems)
    if isinstance(budget.estimated_tokens, int) and isinstance(budget.max_tokens, int):
        if not isinstance(budget.estimated_tokens, bool) and budget.estimated_tokens > budget.max_tokens:
            problems.append("budget.estimated_tokens must be <= budget.max_tokens")
    _check_member("budget.estimator", budget.estimator, ("known", "unknown"), problems)
    if budget.policy != "critical-atoms-lossless":
        problems.append("budget.policy must be 'critical-atoms-lossless'")


def _check_integrity(capsule: Capsule, problems: list[str]) -> None:
    integrity = capsule.integrity
    if not isinstance(integrity, Integrity):
        problems.append("integrity must be an Integrity")
        return
    if integrity.canonicalization != CANONICALIZATION:
        problems.append(f"integrity.canonicalization must be {CANONICALIZATION!r}")
    _check_sha256("integrity.manifest_sha256", integrity.manifest_sha256, problems)
    if integrity.manifest_sha256 != capsule.capsule_id:
        problems.append("integrity.manifest_sha256 must match capsule_id")
    _check_digest_binding(capsule, problems)


def _check_digest_binding(capsule: Capsule, problems: list[str]) -> None:
    try:
        expected = capsule_digest(capsule)
    except (CanonicalJSONError, TypeError, ValueError, AttributeError):
        problems.append("capsule identity payload must be canonical JSON encodable")
        return
    if is_sha256_ref(capsule.capsule_id) and capsule.capsule_id != expected:
        problems.append("capsule_id must match identity digest")


def _check_ordering(capsule: Capsule, problems: list[str]) -> None:
    if isinstance(capsule.atoms, tuple) and all(isinstance(a, CanonAtom) for a in capsule.atoms):
        safe = all(safe_atom_sort_key(a) is not None for a in capsule.atoms)
        if safe and capsule.atoms != tuple(sorted(capsule.atoms, key=atom_sort_key)):
            problems.append("atoms must be sorted by precedence_rank, layer, type, id")
    if isinstance(capsule.records, tuple) and all(isinstance(r, Record) for r in capsule.records):
        if capsule.records != sorted_records(capsule.records):
            problems.append("records must be sorted by scope, id, kind")
    if isinstance(capsule.omissions, tuple) and all(isinstance(o, Omission) for o in capsule.omissions):
        if capsule.omissions != sorted_omissions(capsule.omissions):
            problems.append("omissions must be sorted by reason, critical, decision, affected_ids")
    if isinstance(capsule.lossy_transforms, tuple) and all(isinstance(r, TransformReceipt) for r in capsule.lossy_transforms):
        if capsule.lossy_transforms != sorted_transforms(capsule.lossy_transforms):
            problems.append("lossy_transforms must be sorted by transform, method_id, output_ref")
    if isinstance(capsule.receipts, tuple) and all(isinstance(r, dict) for r in capsule.receipts):
        if capsule.receipts != sorted_receipts(capsule.receipts):
            problems.append("receipts must be sorted by canonical JSON")


def _check_derived_fields(capsule: Capsule, problems: list[str]) -> None:
    if not isinstance(capsule.atoms, tuple) or not all(isinstance(a, CanonAtom) for a in capsule.atoms):
        return
    if any(safe_atom_sort_key(a) is None for a in capsule.atoms):
        return
    if capsule.layers != layers(capsule.atoms):
        problems.append("layers must be derived from sorted atoms")
    if capsule.conflicts != atoms_of_type(capsule.atoms, "conflict"):
        problems.append("conflicts must be derived from atoms")
    if capsule.unknowns != atoms_of_type(capsule.atoms, "unknown"):
        problems.append("unknowns must be derived from atoms")
    if capsule.freshness != freshness(capsule.atoms):
        problems.append("freshness must be derived from atoms")
