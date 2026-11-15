"""Accountable memory -- re-verifiable, witnessed memory records over a provenance graph.

A memory is a reconcile-shaped record: a witnessed claim carrying a *reference* to the
criterion that re-checks it, so on recall it can re-verify itself (MATCH/DRIFT/
UNVERIFIABLE). Stored in a tamper-evident ProvenanceGraph; relationships are typed
edges. Stdlib only. Inert and advisory: it records and re-derives; it grants no authority.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .observation import sha256_hex
from .provenance import ProvenanceGraph, GraphVerdict, VALID, BROKEN

MEMORY_TYPES = ("fact", "pointer", "decision", "pref")
RECORD_ALGO = "memory-record-canonical-v1"


@dataclass(frozen=True)
class CriterionRef:
    name: str
    version: str
    params: tuple[tuple[str, str], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "version": self.version,
                "params": [list(p) for p in self.params]}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CriterionRef":
        return cls(str(d["name"]), str(d["version"]),
                   tuple((str(k), str(v)) for k, v in d.get("params", [])))


@dataclass(frozen=True)
class PerceiveRef:
    name: str
    args: tuple[tuple[str, str], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "args": [list(p) for p in self.args]}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PerceiveRef":
        return cls(str(d["name"]), tuple((str(k), str(v)) for k, v in d.get("args", [])))


@dataclass(frozen=True)
class MemoryRecord:
    id: str
    type: str
    claim: str
    tags: tuple[str, ...] = ()
    criterion_ref: CriterionRef | None = None
    perceive_ref: PerceiveRef | None = None
    created: str = ""  # ISO timestamp; VOLATILE -- excluded from identity

    def __post_init__(self) -> None:
        if self.type not in MEMORY_TYPES:
            raise ValueError(f"unknown memory type {self.type!r}")

    def canonical_bytes(self) -> bytes:
        """Deterministic identity payload. Excludes volatile fields (created)."""
        payload = {
            "algo": RECORD_ALGO,
            "id": self.id, "type": self.type, "claim": self.claim,
            "tags": sorted(self.tags),
            "criterion_ref": self.criterion_ref.to_dict() if self.criterion_ref else None,
            "perceive_ref": self.perceive_ref.to_dict() if self.perceive_ref else None,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True).encode("ascii")

    @property
    def identity_sha256(self) -> str:
        return sha256_hex(self.canonical_bytes())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "type": self.type, "claim": self.claim, "tags": list(self.tags),
            "criterion_ref": self.criterion_ref.to_dict() if self.criterion_ref else None,
            "perceive_ref": self.perceive_ref.to_dict() if self.perceive_ref else None,
            "created": self.created,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "MemoryRecord":
        return cls(
            id=str(d["id"]), type=str(d["type"]), claim=str(d["claim"]),
            tags=tuple(d.get("tags", [])),
            criterion_ref=CriterionRef.from_dict(d["criterion_ref"]) if d.get("criterion_ref") else None,
            perceive_ref=PerceiveRef.from_dict(d["perceive_ref"]) if d.get("perceive_ref") else None,
            created=str(d.get("created", "")),
        )


class MemoryStore:
    """An append-only store of witnessed memory records over a ProvenanceGraph."""

    def __init__(self) -> None:
        self.graph = ProvenanceGraph()
        self.records: dict[str, MemoryRecord] = {}

    def remember(self, record: MemoryRecord, *, parents: tuple | list = (),
                 edge_type: str = "derived-from") -> str:
        """Store a record and add its witnessed node. `parents` are ids of EXISTING
        memories this one relates to via `edge_type` (e.g. 'supersedes')."""
        if record.id in self.records:
            raise ValueError(f"duplicate memory id {record.id!r}")
        self.graph.add(record.id, "memory", record.identity_sha256,
                       parents=tuple(parents), edge_type=edge_type)
        self.records[record.id] = record
        return record.id

    def get(self, id: str) -> MemoryRecord | None:
        return self.records.get(id)

    def verify(self, *, pinned_manifest: str | None = None) -> GraphVerdict:
        """Two-layer integrity: the graph's hash-chain (+ pinned anchor) AND each
        record's content digest vs its node digest. Either failing is BROKEN."""
        gv = self.graph.verify(pinned_manifest=pinned_manifest)
        if gv.verdict != VALID:
            return gv
        reasons: list[str] = []
        for rid, rec in self.records.items():
            node = self.graph.nodes.get(rid)
            if node is None:
                reasons.append(f"record {rid!r} has no graph node")
            elif rec.identity_sha256 != node.digest:
                reasons.append(f"record {rid!r} content digest != node digest (tampered)")
        return GraphVerdict(BROKEN, reasons) if reasons else GraphVerdict(VALID, [])

    def save(self, path) -> None:
        data = {"graph": self.graph.to_dict(),
                "records": [r.to_dict() for r in self.records.values()]}
        Path(path).write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    @classmethod
    def load(cls, path) -> "MemoryStore":
        """Reconstruct the store. Caller runs verify() to re-validate (resume)."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        store = cls()
        store.graph = ProvenanceGraph.from_dict(data["graph"])
        for rd in data.get("records", []):
            rec = MemoryRecord.from_dict(rd)
            store.records[rec.id] = rec
        return store
