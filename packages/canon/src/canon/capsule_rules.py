from __future__ import annotations

import copy

from .atom import CanonAtom, atom_key
from .canonical_json import CanonicalJSONError, canonical_json_text
from .omission import Omission
from .readiness import CRITICAL_SET_KEYS
from .schema import Record
from .transform import TransformReceipt

_CRITICAL_SET_BY_TYPE = {
    "active-goal": "active_goal_ids",
    "permission": "permission_ids",
    "prohibition": "prohibition_ids",
    "constraint": "constraint_ids",
    "frontier-state": "frontier_state_ids",
    "conflict": "unresolved_conflict_ids",
    "unknown": "unknown_ids",
}


def atom_sort_key(atom: CanonAtom) -> tuple[object, ...]:
    return (atom.precedence_rank, atom.layer, atom.type, atom.id)


def safe_atom_sort_key(atom: CanonAtom) -> tuple[int, str, str, str] | None:
    rank, layer, atom_type, atom_id = atom_sort_key(atom)
    if isinstance(rank, bool) or not isinstance(rank, int):
        return None
    if not all(isinstance(v, str) and v != "" for v in (layer, atom_type, atom_id)):
        return None
    return (rank, layer, atom_type, atom_id)


def safe_atom_identity_key(atom: CanonAtom) -> tuple[str, str, str] | None:
    scope_key, atom_type, atom_id = atom_key(atom)
    if not all(isinstance(v, str) and v != "" for v in (scope_key, atom_type, atom_id)):
        return None
    return (scope_key, atom_type, atom_id)


def duplicate_atom_identities(atoms: object) -> tuple[tuple[str, str, str], ...]:
    counts: dict[tuple[str, str, str], int] = {}
    if not isinstance(atoms, (list, tuple)):
        return ()
    for atom in atoms:
        if not isinstance(atom, CanonAtom):
            continue
        key = safe_atom_identity_key(atom)
        if key is not None:
            counts[key] = counts.get(key, 0) + 1
    return tuple(key for key, count in sorted(counts.items()) if count > 1)


def sorted_records(records: tuple[Record, ...]) -> tuple[Record, ...]:
    return tuple(sorted(records, key=lambda r: (r.scope, r.id, r.kind)))


def sorted_omissions(omissions: tuple[Omission, ...]) -> tuple[Omission, ...]:
    return tuple(sorted(omissions, key=lambda o: (o.reason, o.critical, o.decision, o.affected_ids)))


def sorted_transforms(receipts: tuple[TransformReceipt, ...]) -> tuple[TransformReceipt, ...]:
    return tuple(sorted(receipts, key=lambda r: (r.transform, r.method_id, r.output_ref)))


def sorted_receipts(receipts: tuple[dict, ...]) -> tuple[dict, ...]:
    return tuple(sorted((copy.deepcopy(r) for r in receipts), key=receipt_sort_key))


def receipt_sort_key(receipt: dict) -> str:
    try:
        return canonical_json_text(receipt)
    except (CanonicalJSONError, TypeError, ValueError):
        return repr(receipt)


def layers(atoms: tuple[CanonAtom, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for atom in atoms:
        if atom.layer not in seen:
            seen.add(atom.layer)
            result.append(atom.layer)
    return tuple(result)


def atoms_of_type(atoms: tuple[CanonAtom, ...], atom_type: str) -> tuple[CanonAtom, ...]:
    return tuple(atom for atom in atoms if atom.type == atom_type)


def freshness(atoms: tuple[CanonAtom, ...]) -> tuple[dict, ...]:
    return tuple(freshness_row(atom) for atom in atoms if atom.freshness)


def freshness_row(atom: CanonAtom) -> dict:
    return {"id": atom.id, "type": atom.type, "status": atom.status, "freshness": copy.deepcopy(atom.freshness)}


def critical_sets(atoms: tuple[CanonAtom, ...]) -> dict:
    result = {key: [] for key in CRITICAL_SET_KEYS}
    for atom in atoms:
        if atom.critical is True and atom.type in _CRITICAL_SET_BY_TYPE:
            result[_CRITICAL_SET_BY_TYPE[atom.type]].append(atom.id)
    return result
