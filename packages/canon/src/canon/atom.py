from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from typing import ClassVar, Iterable

from .canonical_json import canonical_json_text, canonical_sha256
from .schema import Record
from .validator import validate_record

ATOM_SCHEMA = "canon.atom/v1"
ATOM_TYPES = (
    "instruction",
    "active-goal",
    "permission",
    "prohibition",
    "constraint",
    "decision",
    "frontier-state",
    "evidence-ref",
    "episodic-fact",
    "synthesized-persona",
    "conflict",
    "unknown",
    "omission",
    "lossy-transform",
    "bootstrap-probe",
    "bootstrap-witness",
    "adapter-capability",
)
ATOM_LAYERS = (
    "session",
    "task",
    "project",
    "repo",
    "workspace",
    "personal",
    "team",
    "organization",
    "imported-history",
)
ATOM_STATUSES = ("active", "retired", "superseded", "stale", "contradictory", "untrusted", "unknown", "blocked")
ATOM_CLASSIFICATIONS = ("normative", "descriptive", "derived", "receipt")

_CRITICAL_TYPES = frozenset({
    "active-goal",
    "permission",
    "prohibition",
    "constraint",
    "frontier-state",
    "conflict",
    "unknown",
})
_LIVE_CRITICAL_STATUSES = frozenset({"active", "blocked", "unknown", "stale", "contradictory", "untrusted"})
_KIND_MAP = {
    "personality-block": ("instruction", "normative"),
    "adr-decision": ("decision", "descriptive"),
    "research-artifact-ref": ("evidence-ref", "descriptive"),
    "episodic-memory": ("episodic-fact", "descriptive"),
    "synthesized-persona-l3": ("synthesized-persona", "derived"),
}
_SCOPE_MAP = {
    "workspace": ("workspace", "record-scope:workspace", 4),
    "global": ("personal", "record-scope:global", 6),
}


@dataclass(frozen=True, slots=True)
class CanonAtom:
    type: str
    id: str
    layer: str
    scope_key: str
    precedence_rank: int
    status: str
    classification: str
    critical: bool
    value: dict
    source_refs: tuple[dict, ...] = ()
    source_span_refs: tuple[dict, ...] = ()
    freshness: dict = field(default_factory=dict)
    trust: dict = field(default_factory=dict)
    disclosure: dict = field(default_factory=dict)
    hashes: dict = field(default_factory=dict)

    atom_schema: ClassVar[str] = ATOM_SCHEMA

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", copy.deepcopy(self.value))
        object.__setattr__(self, "source_refs", _copy_tuple(self.source_refs))
        object.__setattr__(self, "source_span_refs", _copy_tuple(self.source_span_refs))
        object.__setattr__(self, "freshness", copy.deepcopy(self.freshness))
        object.__setattr__(self, "trust", copy.deepcopy(self.trust))
        object.__setattr__(self, "disclosure", copy.deepcopy(self.disclosure))
        object.__setattr__(self, "hashes", copy.deepcopy(self.hashes))

    def to_dict(self) -> dict:
        return {
            "atom_schema": ATOM_SCHEMA,
            "type": self.type,
            "id": self.id,
            "layer": self.layer,
            "scope_key": self.scope_key,
            "precedence_rank": self.precedence_rank,
            "status": self.status,
            "classification": self.classification,
            "critical": self.critical,
            "value": copy.deepcopy(self.value),
            "source_refs": [copy.deepcopy(ref) for ref in self.source_refs],
            "source_span_refs": [copy.deepcopy(ref) for ref in self.source_span_refs],
            "freshness": copy.deepcopy(self.freshness),
            "trust": copy.deepcopy(self.trust),
            "disclosure": copy.deepcopy(self.disclosure),
            "hashes": copy.deepcopy(self.hashes),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CanonAtom":
        if not isinstance(d, dict):
            raise TypeError(f"atom JSON must be an object, got {type(d).__name__}")
        got = d.get("atom_schema")
        if got != ATOM_SCHEMA:
            raise ValueError(f"expected atom_schema {ATOM_SCHEMA!r}, got {got!r}")
        return cls(
            type=d["type"],
            id=d["id"],
            layer=d["layer"],
            scope_key=d["scope_key"],
            precedence_rank=d["precedence_rank"],
            status=d["status"],
            classification=d["classification"],
            critical=d["critical"],
            value=copy.deepcopy(d["value"]),
            source_refs=_copy_tuple(d["source_refs"]),
            source_span_refs=_copy_tuple(d["source_span_refs"]),
            freshness=copy.deepcopy(d["freshness"]),
            trust=copy.deepcopy(d["trust"]),
            disclosure=copy.deepcopy(d["disclosure"]),
            hashes=copy.deepcopy(d["hashes"]),
        )

    def to_json(self) -> str:
        return canonical_json_text(self.to_dict())

    @classmethod
    def from_json(cls, text: str) -> "CanonAtom":
        return cls.from_dict(json.loads(text))


def atom_key(atom: CanonAtom) -> tuple[str, str, str]:
    return (atom.scope_key, atom.type, atom.id)


def atoms_from_records(records: Iterable[Record]) -> list[CanonAtom]:
    recs = tuple(records)
    problems = _record_problems(recs)
    if problems:
        raise ValueError("; ".join(problems))
    atoms = [_atom_from_record(record) for record in recs]
    return sorted(atoms, key=lambda a: (a.precedence_rank, a.layer, a.type, a.id))


def load_atoms_jsonl(text: str) -> list[CanonAtom]:
    atoms: list[CanonAtom] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        atoms.append(_load_atom_line(line, lineno))
    return atoms


def validate_atom(atom: object) -> list[str]:
    if not isinstance(atom, CanonAtom):
        return [f"atom must be a CanonAtom, got {type(atom).__name__}"]
    problems: list[str] = []
    _check_enum_fields(atom, problems)
    _check_text_key("id", atom.id, problems)
    _check_text_key("scope_key", atom.scope_key, problems)
    _check_rank_and_critical(atom, problems)
    _check_dict_fields(atom, problems)
    _check_ref_tuple("source_refs", atom.source_refs, problems)
    _check_ref_tuple("source_span_refs", atom.source_span_refs, problems)
    return problems


def is_valid_atom(atom: object) -> bool:
    return not validate_atom(atom)


def _copy_tuple(value: Iterable[dict]) -> tuple[dict, ...]:
    return tuple(copy.deepcopy(item) for item in value)


def _record_problems(records: tuple[Record, ...]) -> list[str]:
    problems: list[str] = []
    for record in records:
        for problem in validate_record(record):
            problems.append(f"record {record.id}: {problem}")
    return problems


def _atom_from_record(record: Record) -> CanonAtom:
    atom_type, classification = _KIND_MAP[record.kind]
    layer, scope_key, rank = _SCOPE_MAP[record.scope]
    valid_until = record.temporal.valid_until if record.temporal is not None else None
    freshness = {"state": "superseded", "valid_until": valid_until}
    status = "superseded"
    if valid_until is None:
        freshness = {"state": "current"}
        status = "active"
    return CanonAtom(
        type=atom_type,
        id=record.id,
        layer=layer,
        scope_key=scope_key,
        precedence_rank=rank,
        status=status,
        classification=classification,
        critical=False,
        value=record.data,
        source_refs=(_record_source_ref(record),),
        freshness=freshness,
        trust={"label": "trusted-local", "harness": record.provenance.harness},
        disclosure={"profile": "project-only"},
        hashes={"record_sha256": canonical_sha256(record.to_dict())},
    )


def _record_source_ref(record: Record) -> dict:
    return {
        "ref": f"record:{record.scope}/{record.id}",
        "kind": record.kind,
        "source_hash": record.provenance.source_hash,
    }


def _load_atom_line(line: str, lineno: int) -> CanonAtom:
    try:
        atom = CanonAtom.from_json(line)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"line {lineno}: {exc}") from exc
    problems = validate_atom(atom)
    if problems:
        raise ValueError(f"line {lineno}: {'; '.join(problems)}")
    return atom


def _check_enum_fields(atom: CanonAtom, problems: list[str]) -> None:
    _check_member("type", atom.type, ATOM_TYPES, problems)
    _check_member("layer", atom.layer, ATOM_LAYERS, problems)
    _check_member("status", atom.status, ATOM_STATUSES, problems)
    _check_member("classification", atom.classification, ATOM_CLASSIFICATIONS, problems)


def _check_member(name: str, value: str, allowed: tuple[str, ...], problems: list[str]) -> None:
    if value not in allowed:
        problems.append(f"{name} must be one of {list(allowed)}, got {value!r}")


def _check_text_key(name: str, value: object, problems: list[str]) -> None:
    if not isinstance(value, str) or value == "":
        problems.append(f"{name} must be a non-empty string")
    elif "\r" in value or "\n" in value:
        problems.append(f"{name} may not contain CR or LF")


def _check_rank_and_critical(atom: CanonAtom, problems: list[str]) -> None:
    rank = atom.precedence_rank
    if not isinstance(rank, int) or isinstance(rank, bool) or rank < 0:
        problems.append("precedence_rank must be a non-negative int")
    if not isinstance(atom.critical, bool):
        problems.append("critical must be bool")
    if _retired_critical_normative(atom):
        problems.append("critical normative atom status cannot be retired or superseded")


def _retired_critical_normative(atom: CanonAtom) -> bool:
    return (
        atom.critical is True
        and atom.classification == "normative"
        and atom.type in _CRITICAL_TYPES
        and atom.status not in _LIVE_CRITICAL_STATUSES
    )


def _check_dict_fields(atom: CanonAtom, problems: list[str]) -> None:
    for name in ("value", "freshness", "trust", "disclosure", "hashes"):
        if not isinstance(getattr(atom, name), dict):
            problems.append(f"{name} must be a dict")


def _check_ref_tuple(name: str, value: object, problems: list[str]) -> None:
    if not isinstance(value, tuple):
        problems.append(f"{name} must be a tuple")
        return
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            problems.append(f"{name}[{index}] must be a dict")
