from __future__ import annotations

from dataclasses import replace
from importlib import import_module
from typing import Iterable

from .atom import CanonAtom, atoms_from_records
from .canonical_json import CanonicalJSONError
from .capsule_rules import (
    atom_sort_key,
    atoms_of_type,
    critical_sets,
    duplicate_atom_identities,
    freshness,
    layers,
    sorted_omissions,
    sorted_receipts,
    sorted_records,
    sorted_transforms,
)
from .capsule_types import (
    CANONICALIZATION,
    Budget,
    Capsule,
    CapsuleBuildError,
    CapsuleBundle,
    CapsuleCompileRequest,
    CapsuleTarget,
    Compatibility,
    Integrity,
    SourceState,
    capsule_bytes,
    capsule_digest,
)
from .capsule_validation import validate_capsule
from .omission import Omission
from .readiness import CRITICAL_SET_KEYS, ReadinessProbe
from .schema import Record
from .transform import TransformReceipt


def compile_capsule(request: CapsuleCompileRequest) -> CapsuleBundle:
    render_canon_md = import_module("canon.canonmd").render_canon_md
    capsule = build_capsule(
        profile=request.profile, target=request.target, source_state=request.source_state,
        budget=request.budget, atoms=request.atoms, records=request.records,
        omissions=request.omissions, lossy_transforms=request.lossy_transforms,
        receipts=request.receipts, does_not_prove=request.does_not_prove,
        required_atom_ids=request.required_atom_ids,
    )
    probe = ReadinessProbe(request.readiness_probe_id, capsule.capsule_id, request.readiness_target or capsule.target.to_dict(), critical_sets(capsule.atoms), {"format": "json", "required_fields": list(CRITICAL_SET_KEYS)}, {"method": "exact-id-set-and-status-match", "pass_threshold": "all-critical"})
    return CapsuleBundle(capsule, capsule_bytes(capsule), render_canon_md(capsule), probe)


def build_capsule(
    *,
    profile: str,
    target: CapsuleTarget,
    source_state: SourceState,
    budget: Budget,
    atoms: Iterable[CanonAtom],
    records: Iterable[Record] = (),
    omissions: Iterable[Omission] = (),
    lossy_transforms: Iterable[TransformReceipt] = (),
    receipts: Iterable[dict] = (),
    does_not_prove: Iterable[str] = (),
    required_atom_ids: Iterable[str] = (),
) -> Capsule:
    record_items = tuple(records)
    atom_items = tuple(atoms) + _atoms_from_records(record_items)
    _raise_build_problems(f"atoms contain duplicate atom identity {k!r}" for k in duplicate_atom_identities(atom_items))
    sorted_atoms = _sort_atoms(atom_items)
    _check_required_atoms(sorted_atoms, tuple(required_atom_ids))
    draft = Capsule(
        "", profile, target, source_state, Compatibility(), budget,
        layers(sorted_atoms), sorted_atoms, sorted_records(record_items),
        atoms_of_type(sorted_atoms, "conflict"), atoms_of_type(sorted_atoms, "unknown"),
        sorted_omissions(tuple(omissions)), sorted_transforms(tuple(lossy_transforms)),
        freshness(sorted_atoms), Integrity(CANONICALIZATION, ""),
        sorted_receipts(tuple(receipts)), tuple(does_not_prove),
    )
    return _validated_final_capsule(draft)


def _atoms_from_records(records: tuple[Record, ...]) -> tuple[CanonAtom, ...]:
    try:
        return tuple(atoms_from_records(records))
    except ValueError as exc:
        raise CapsuleBuildError(str(exc)) from exc


def _sort_atoms(atoms: tuple[CanonAtom, ...]) -> tuple[CanonAtom, ...]:
    try:
        return tuple(sorted(atoms, key=atom_sort_key))
    except TypeError as exc:
        raise CapsuleBuildError(f"atoms must be sortable by precedence_rank, layer, type, id: {exc}") from exc


def _validated_final_capsule(draft: Capsule) -> Capsule:
    try:
        digest = capsule_digest(draft)
    except (CanonicalJSONError, TypeError, ValueError, AttributeError) as exc:
        raise CapsuleBuildError(f"capsule identity payload must be canonical JSON encodable: {exc}") from exc
    final = replace(draft, capsule_id=digest, integrity=Integrity(CANONICALIZATION, digest))
    _raise_build_problems(validate_capsule(final))
    return final


def _raise_build_problems(problems: Iterable[str]) -> None:
    ordered = tuple(sorted(str(problem) for problem in problems))
    if ordered:
        raise CapsuleBuildError("; ".join(ordered))


def _check_required_atoms(atoms: tuple[CanonAtom, ...], required_ids: tuple[str, ...]) -> None:
    identities_by_id: dict[str, set[tuple[str, str, str]]] = {}
    atoms_by_id: dict[str, list[CanonAtom]] = {}
    for atom in atoms:
        if isinstance(atom.id, str):
            identities_by_id.setdefault(atom.id, set()).add((atom.scope_key, atom.type, atom.id))
            atoms_by_id.setdefault(atom.id, []).append(atom)
    for required_id in required_ids:
        identities = identities_by_id.get(required_id, set())
        if len(identities) > 1:
            raise CapsuleBuildError(f"required atom {required_id!r} is ambiguous: {tuple(sorted(identities))!r}")
        atom = next(iter(atoms_by_id.get(required_id, ())), None)
        if atom is None:
            raise CapsuleBuildError(f"required atom {required_id!r} is missing")
        if atom.critical is not True:
            raise CapsuleBuildError(f"required atom {required_id!r} is not critical")
