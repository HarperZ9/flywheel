from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Callable, ClassVar

from .atom import CanonAtom
from .canonical_json import (
    CANONICALIZATION as JSON_CANONICALIZATION,
    canonical_json_bytes,
    canonical_json_text,
    canonical_sha256,
)
from .omission import Omission
from .readiness import ReadinessProbe
from .schema import SCHEMA as RECORD_SCHEMA, Record
from .transform import TransformReceipt

CAPSULE_SCHEMA = "canon.capsule/v1"
CAPSULE_PROFILES = ("needle", "handoff", "archive", "custom")
CANONICALIZATION = JSON_CANONICALIZATION
SOURCE_STATE_DIGEST_KEYS = ("records_digest", "inventory_digest", "context_envelope_digest", "mneme_snapshot_digest", "relay_checkpoint", "worktree_digest")


class CapsuleError(ValueError):
    pass


class CapsuleBuildError(CapsuleError):
    pass


@dataclass(frozen=True, slots=True)
class CapsuleTarget:
    adapter: str
    surface: str
    integration_tier: str
    host_enforcement_observed: bool = False

    def to_dict(self) -> dict:
        return {"adapter": self.adapter, "surface": self.surface, "integration_tier": self.integration_tier, "host_enforcement_observed": self.host_enforcement_observed}

    @classmethod
    def from_dict(cls, d: dict) -> "CapsuleTarget":
        if not isinstance(d, dict):
            raise TypeError(f"capsule target JSON must be an object, got {type(d).__name__}")
        return cls(d["adapter"], d["surface"], d["integration_tier"], d.get("host_enforcement_observed", False))


@dataclass(frozen=True, slots=True)
class SourceState:
    records_digest: str
    inventory_digest: str | None = None
    context_envelope_digest: str | None = None
    mneme_snapshot_digest: str | None = None
    relay_checkpoint: str | None = None
    worktree_digest: str | None = None

    def to_dict(self) -> dict:
        return {"records_digest": self.records_digest, "inventory_digest": self.inventory_digest, "context_envelope_digest": self.context_envelope_digest, "mneme_snapshot_digest": self.mneme_snapshot_digest, "relay_checkpoint": self.relay_checkpoint, "worktree_digest": self.worktree_digest}

    @classmethod
    def from_dict(cls, d: dict) -> "SourceState":
        if not isinstance(d, dict):
            raise TypeError(f"source state JSON must be an object, got {type(d).__name__}")
        return cls(d["records_digest"], d.get("inventory_digest"), d.get("context_envelope_digest"), d.get("mneme_snapshot_digest"), d.get("relay_checkpoint"), d.get("worktree_digest"))


@dataclass(frozen=True, slots=True)
class Compatibility:
    record_schema_min: str = RECORD_SCHEMA
    capsule_schema: str = CAPSULE_SCHEMA
    requires_features: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "requires_features", _tuple_sequence(self.requires_features))

    def to_dict(self) -> dict:
        return {"record_schema_min": self.record_schema_min, "capsule_schema": self.capsule_schema, "requires_features": _json_sequence(self.requires_features)}

    @classmethod
    def from_dict(cls, d: dict) -> "Compatibility":
        if not isinstance(d, dict):
            raise TypeError(f"compatibility JSON must be an object, got {type(d).__name__}")
        return cls(d["record_schema_min"], d["capsule_schema"], d["requires_features"])


@dataclass(frozen=True, slots=True)
class Budget:
    profile: str
    max_tokens: int
    estimated_tokens: int
    estimator: str
    policy: str = "critical-atoms-lossless"

    def to_dict(self) -> dict:
        return {"profile": self.profile, "max_tokens": self.max_tokens, "estimated_tokens": self.estimated_tokens, "estimator": self.estimator, "policy": self.policy}

    @classmethod
    def from_dict(cls, d: dict) -> "Budget":
        if not isinstance(d, dict):
            raise TypeError(f"budget JSON must be an object, got {type(d).__name__}")
        return cls(d["profile"], d["max_tokens"], d["estimated_tokens"], d["estimator"], d.get("policy", "critical-atoms-lossless"))


@dataclass(frozen=True, slots=True)
class Integrity:
    canonicalization: str
    manifest_sha256: str

    def to_dict(self) -> dict:
        return {"canonicalization": self.canonicalization, "manifest_sha256": self.manifest_sha256}

    @classmethod
    def from_dict(cls, d: dict) -> "Integrity":
        if not isinstance(d, dict):
            raise TypeError(f"integrity JSON must be an object, got {type(d).__name__}")
        return cls(d["canonicalization"], d["manifest_sha256"])


@dataclass(frozen=True, slots=True)
class Capsule:
    capsule_id: str
    profile: str
    target: CapsuleTarget
    source_state: SourceState
    compatibility: Compatibility
    budget: Budget
    layers: tuple[str, ...]
    atoms: tuple[CanonAtom, ...]
    records: tuple[Record, ...]
    conflicts: tuple[CanonAtom, ...]
    unknowns: tuple[CanonAtom, ...]
    omissions: tuple[Omission, ...]
    lossy_transforms: tuple[TransformReceipt, ...]
    freshness: tuple[dict, ...]
    integrity: Integrity
    receipts: tuple[dict, ...]
    does_not_prove: tuple[str, ...]
    schema: ClassVar[str] = CAPSULE_SCHEMA

    def __post_init__(self) -> None:
        object.__setattr__(self, "target", _value_of(self.target, CapsuleTarget.from_dict))
        object.__setattr__(self, "source_state", _value_of(self.source_state, SourceState.from_dict))
        object.__setattr__(self, "compatibility", _value_of(self.compatibility, Compatibility.from_dict))
        object.__setattr__(self, "budget", _value_of(self.budget, Budget.from_dict))
        object.__setattr__(self, "integrity", _value_of(self.integrity, Integrity.from_dict))
        object.__setattr__(self, "layers", _tuple_sequence(self.layers))
        object.__setattr__(self, "atoms", _tuple_of(self.atoms, CanonAtom.from_dict))
        object.__setattr__(self, "records", _tuple_of(self.records, Record.from_dict))
        object.__setattr__(self, "conflicts", _tuple_of(self.conflicts, CanonAtom.from_dict))
        object.__setattr__(self, "unknowns", _tuple_of(self.unknowns, CanonAtom.from_dict))
        object.__setattr__(self, "omissions", _tuple_of(self.omissions, Omission.from_dict))
        object.__setattr__(self, "lossy_transforms", _tuple_of(self.lossy_transforms, TransformReceipt.from_dict))
        object.__setattr__(self, "freshness", _tuple_sequence(self.freshness))
        object.__setattr__(self, "receipts", _tuple_sequence(self.receipts))
        object.__setattr__(self, "does_not_prove", _tuple_sequence(self.does_not_prove))

    def to_dict(self, *, identity: bool = True) -> dict:
        result = {
            "schema": CAPSULE_SCHEMA, "capsule_id": self.capsule_id if identity else "",
            "profile": self.profile, "target": _value_to_dict(self.target, CapsuleTarget),
            "source_state": _value_to_dict(self.source_state, SourceState),
            "compatibility": _value_to_dict(self.compatibility, Compatibility),
            "budget": _value_to_dict(self.budget, Budget), "layers": _json_sequence(self.layers),
            "atoms": _items_to_json(self.atoms, CanonAtom), "records": _items_to_json(self.records, Record),
            "conflicts": _items_to_json(self.conflicts, CanonAtom), "unknowns": _items_to_json(self.unknowns, CanonAtom),
            "omissions": _items_to_json(self.omissions, Omission), "lossy_transforms": _items_to_json(self.lossy_transforms, TransformReceipt),
            "freshness": _json_sequence(self.freshness), "integrity": _value_to_dict(self.integrity, Integrity),
            "receipts": _json_sequence(self.receipts), "does_not_prove": _json_sequence(self.does_not_prove),
        }
        if not identity:
            _blank_manifest_sha256(result)
        return result

    @classmethod
    def from_dict(cls, d: dict) -> "Capsule":
        if not isinstance(d, dict):
            raise TypeError(f"capsule JSON must be an object, got {type(d).__name__}")
        got = d.get("schema")
        if got != CAPSULE_SCHEMA:
            raise ValueError(f"expected schema {CAPSULE_SCHEMA!r}, got {got!r}")
        return cls(d["capsule_id"], d["profile"], d["target"], d["source_state"], d["compatibility"], d["budget"], d["layers"], d["atoms"], d["records"], d["conflicts"], d["unknowns"], d["omissions"], d["lossy_transforms"], d["freshness"], d["integrity"], d["receipts"], d.get("does_not_prove", ()))

    def to_json(self) -> str:
        return canonical_json_text(self.to_dict())


@dataclass(frozen=True, slots=True)
class CapsuleCompileRequest:
    profile: str
    target: CapsuleTarget
    source_state: SourceState
    budget: Budget
    atoms: tuple[CanonAtom, ...] = ()
    records: tuple[Record, ...] = ()
    omissions: tuple[Omission, ...] = ()
    lossy_transforms: tuple[TransformReceipt, ...] = ()
    receipts: tuple[dict, ...] = ()
    does_not_prove: tuple[str, ...] = ()
    required_atom_ids: tuple[str, ...] = ()
    readiness_probe_id: str = "readiness-default"
    readiness_target: dict | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "target", _value_of(self.target, CapsuleTarget.from_dict))
        object.__setattr__(self, "source_state", _value_of(self.source_state, SourceState.from_dict))
        object.__setattr__(self, "budget", _value_of(self.budget, Budget.from_dict))
        object.__setattr__(self, "atoms", _tuple_of(self.atoms, CanonAtom.from_dict))
        object.__setattr__(self, "records", _tuple_of(self.records, Record.from_dict))
        object.__setattr__(self, "omissions", _tuple_of(self.omissions, Omission.from_dict))
        object.__setattr__(self, "lossy_transforms", _tuple_of(self.lossy_transforms, TransformReceipt.from_dict))
        object.__setattr__(self, "receipts", _tuple_sequence(self.receipts))
        object.__setattr__(self, "does_not_prove", _tuple_sequence(self.does_not_prove))
        object.__setattr__(self, "required_atom_ids", _tuple_sequence(self.required_atom_ids))
        object.__setattr__(self, "readiness_target", copy.deepcopy(self.readiness_target))


@dataclass(frozen=True, slots=True)
class CapsuleBundle:
    capsule: Capsule
    manifest_bytes: bytes
    canon_md: str
    readiness_probe: ReadinessProbe


def capsule_identity_dict(capsule: Capsule) -> dict:
    return capsule.to_dict(identity=False)


def capsule_digest(capsule: Capsule) -> str:
    return canonical_sha256(capsule_identity_dict(capsule))


def capsule_bytes(capsule: Capsule) -> bytes:
    return canonical_json_bytes(capsule.to_dict())


def _value_of(value: object, factory: Callable[[dict], object]) -> object:
    if not isinstance(value, dict):
        return copy.deepcopy(value)
    try:
        return factory(value)
    except (KeyError, TypeError, ValueError):
        return copy.deepcopy(value)


def _tuple_of(value: object, factory: Callable[[dict], object]) -> object:
    if not isinstance(value, (list, tuple)):
        return copy.deepcopy(value)
    return tuple(_value_of(item, factory) for item in value)


def _tuple_sequence(value: object) -> object:
    if isinstance(value, (list, tuple)):
        return tuple(copy.deepcopy(item) for item in value)
    return copy.deepcopy(value)


def _json_sequence(value: object) -> object:
    if isinstance(value, (list, tuple)):
        return [copy.deepcopy(item) for item in value]
    return copy.deepcopy(value)


def _items_to_json(value: object, item_type: type) -> object:
    if not isinstance(value, (list, tuple)):
        return copy.deepcopy(value)
    return [item.to_dict() if isinstance(item, item_type) else copy.deepcopy(item) for item in value]


def _value_to_dict(value: object, value_type: type) -> object:
    return value.to_dict() if isinstance(value, value_type) else copy.deepcopy(value)


def _blank_manifest_sha256(result: dict) -> None:
    integrity = result.get("integrity")
    if isinstance(integrity, dict):
        integrity["manifest_sha256"] = ""
