"""Immutable canonical-byte authority for forged Plan execution."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json

from .evidence_json import strict_load_json


class PlanRunSnapshotError(ValueError):
    """A Plan value is outside the bounded canonical JSON domain."""


@dataclass(frozen=True, slots=True)
class FrozenJsonSnapshot:
    canonical: bytes = field(repr=False)
    sha256: str


def _admit(value: object, remaining: list[int], active: set[int], depth: int):
    remaining[0] -= 1
    if remaining[0] < 0 or depth > 16:
        raise PlanRunSnapshotError()
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) not in (list, dict):
        raise PlanRunSnapshotError()
    identity = id(value)
    if identity in active:
        raise PlanRunSnapshotError()
    active.add(identity)
    try:
        if type(value) is list:
            return [_admit(item, remaining, active, depth + 1)
                    for item in value]
        if not all(type(key) is str for key in value):
            raise PlanRunSnapshotError()
        return {key: _admit(item, remaining, active, depth + 1)
                for key, item in value.items()}
    finally:
        active.remove(identity)


def freeze_json(value: object, *, max_bytes: int | None = None
                ) -> FrozenJsonSnapshot:
    """Copy one bounded object into strict canonical UTF-8 bytes."""
    if type(value) is not dict:
        raise PlanRunSnapshotError()
    try:
        admitted = _admit(value, [4096], set(), 0)
        canonical = json.dumps(
            admitted, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False).encode("utf-8", "strict")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise PlanRunSnapshotError() from None
    if max_bytes is not None and len(canonical) > max_bytes:
        raise PlanRunSnapshotError()
    return FrozenJsonSnapshot(canonical, hashlib.sha256(canonical).hexdigest())


def thaw_json(snapshot: FrozenJsonSnapshot) -> dict:
    """Verify and decode a fresh non-authoritative graph from frozen bytes."""
    if not isinstance(snapshot, FrozenJsonSnapshot):
        raise PlanRunSnapshotError()
    digest = hashlib.sha256(snapshot.canonical).hexdigest()
    if digest != snapshot.sha256:
        raise PlanRunSnapshotError()
    try:
        value = strict_load_json(snapshot.canonical, max_depth=17)
        rebuilt = freeze_json(value)
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise PlanRunSnapshotError() from None
    if rebuilt != snapshot:
        raise PlanRunSnapshotError()
    return value


@dataclass(frozen=True, slots=True)
class PlanRunBinding:
    snapshot: FrozenJsonSnapshot = field(repr=False)
    prp_id: str
    prp_sha256: str
    prompt_sha256: str
    gates_sha256: str
    seal_sha256: str
    binding_sha256: str

    @property
    def prp(self) -> dict:
        return thaw_json(self.snapshot)["prp"]

    @property
    def prompt(self) -> str:
        return thaw_json(self.snapshot)["prompt"]

    @property
    def gates(self) -> list:
        return thaw_json(self.snapshot)["gates"]

    def to_dict(self) -> dict:
        return thaw_json(self.snapshot)


@dataclass(frozen=True, slots=True)
class ForgeRecord:
    snapshot: FrozenJsonSnapshot = field(repr=False)
    owner_ref: str
    prp_id: str
    prp_sha256: str
    prompt_sha256: str
    gates_sha256: str
    created_at: str
    seal_sha256: str

    @property
    def prp(self) -> dict:
        return thaw_json(self.snapshot)["prp"]

    def to_dict(self) -> dict:
        return thaw_json(self.snapshot)


@dataclass(frozen=True, slots=True)
class VerifiedPlanRun:
    binding: PlanRunBinding = field(repr=False)
    record: ForgeRecord = field(repr=False)
