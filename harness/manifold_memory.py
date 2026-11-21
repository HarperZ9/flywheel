"""manifold_memory.py -- Symmetry-Manifold Witnessed Memory for Flywheel.

Packs provenance-bound memory records onto explicit geometric symmetry
manifolds into a fixed-budget capsule whose digest is re-derivable offline
without any black-box encoder:
  - circular: phase angle(s) theta in [0, 2*pi) with geodesic angular distance.
  - rippled-1d: arc-length t with harmonic ripple (cos(k*t), sin(k*t)).
  - linear: Euclidean coordinates (x, y, ...).
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

CAPSULE_SCHEMA = "flywheel.manifold-capsule/v1"
PROVENANCE_SCHEMA = "flywheel.manifold-provenance/v1"

MANIFOLD_CIRCULAR = "circular"
MANIFOLD_RIPPLED_1D = "rippled-1d"
MANIFOLD_LINEAR = "linear"
SUPPORTED_MANIFOLDS = frozenset({MANIFOLD_CIRCULAR, MANIFOLD_RIPPLED_1D, MANIFOLD_LINEAR})

VERDICT_MATCH = "MATCH"
VERDICT_DRIFT = "DRIFT"
VERDICT_UNVERIFIABLE = "UNVERIFIABLE"

DEFAULT_BUDGET_SLOTS = 16
MAX_SUMMARY_CHARS = 240
_TWO_PI = 2.0 * math.pi
_HEX_CHARS = frozenset("0123456789abcdef")


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _is_sha256_hex(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in _HEX_CHARS for c in value.lower())


def _normalize_coords(manifold: str, coords: Sequence[float] | float) -> tuple[float, ...]:
    if manifold not in SUPPORTED_MANIFOLDS:
        raise ValueError(f"unsupported manifold: {manifold!r}")
    if isinstance(coords, (int, float)) and not isinstance(coords, bool):
        seq: tuple[Any, ...] = (coords,)
    elif isinstance(coords, Sequence) and not isinstance(coords, (str, bytes)):
        seq = tuple(coords)
    else:
        raise TypeError("coords must be a number or sequence of numbers")
    if not seq:
        raise ValueError("coords must be non-empty")
    floats: list[float] = []
    for item in seq:
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item):
            raise ValueError("all coordinates must be finite numbers")
        floats.append(float(item))
    if manifold == MANIFOLD_CIRCULAR:
        return tuple(v % _TWO_PI for v in floats)
    if manifold == MANIFOLD_RIPPLED_1D:
        if len(floats) not in (1, 2):
            raise ValueError("rippled-1d coords must be (t,) or (t, k)")
        return (floats[0], floats[1] if len(floats) == 2 else 1.0)
    return tuple(floats)


def embed_rippled_1d(t: float, k: float = 1.0) -> tuple[float, float, float]:
    """Embed 1D arc-length t onto the harmonic ripple curve (t, cos(k*t), sin(k*t))."""
    return (t, math.cos(k * t), math.sin(k * t))


def manifold_distance(
    manifold: str, a: Sequence[float] | float, b: Sequence[float] | float
) -> float:
    """Compute geodesic distance on the named symmetry manifold."""
    ca = _normalize_coords(manifold, a)
    cb = _normalize_coords(manifold, b)
    if manifold == MANIFOLD_CIRCULAR:
        if len(ca) != len(cb):
            raise ValueError("circular coordinate dimensions must match")
        return math.sqrt(sum((abs((x - y + math.pi) % _TWO_PI - math.pi)) ** 2 for x, y in zip(ca, cb)))
    if manifold == MANIFOLD_RIPPLED_1D:
        return math.dist(embed_rippled_1d(ca[0], ca[1]), embed_rippled_1d(cb[0], cb[1]))
    if len(ca) != len(cb):
        raise ValueError("linear coordinate dimensions must match")
    return math.dist(ca, cb)


@dataclass(frozen=True)
class ManifoldRecord:
    """A single provenance-bound memory item anchored to a symmetry manifold."""

    record_id: str
    manifold: str
    coords: tuple[float, ...]
    summary: str
    source_sha256: str
    weight: float = 1.0

    def __post_init__(self) -> None:
        if not isinstance(self.record_id, str) or not self.record_id.strip():
            raise ValueError("record_id must be a non-empty string")
        object.__setattr__(self, "coords", _normalize_coords(self.manifold, self.coords))
        if not isinstance(self.summary, str):
            raise ValueError("summary must be a string")
        if not _is_sha256_hex(self.source_sha256):
            raise ValueError("source_sha256 must be a 64-character hex SHA-256 digest")
        object.__setattr__(self, "source_sha256", self.source_sha256.lower())
        if isinstance(self.weight, bool) or not isinstance(self.weight, (int, float)):
            raise ValueError("weight must be a finite number >= 0.0")
        if not math.isfinite(self.weight) or self.weight < 0.0:
            raise ValueError("weight must be a finite number >= 0.0")


def compute_capsule_sha256(capsule: Mapping[str, Any]) -> str:
    """Re-derive the deterministic SHA-256 digest of a memory capsule offline."""
    return _canonical_sha256({k: v for k, v in capsule.items() if k != "capsule_sha256"})


def compile_memory_capsule(
    records: Sequence[ManifoldRecord],
    query_manifold: str,
    query_coords: Sequence[float] | float,
    *,
    budget_slots: int = DEFAULT_BUDGET_SLOTS,
) -> dict[str, Any]:
    """Select and pack up to budget_slots memory slots ranked by proximity * weight."""
    if isinstance(budget_slots, bool) or not isinstance(budget_slots, int) or budget_slots < 0:
        raise ValueError("budget_slots must be an integer >= 0")
    q_coords = _normalize_coords(query_manifold, query_coords)

    scored: list[tuple[float, float, str, str, ManifoldRecord]] = []
    for rec in records:
        if rec.manifold != query_manifold:
            continue
        if query_manifold != MANIFOLD_RIPPLED_1D and len(rec.coords) != len(q_coords):
            continue
        dist = manifold_distance(query_manifold, rec.coords, q_coords)
        scored.append(((1.0 / (1.0 + dist)) * rec.weight, dist, rec.record_id, rec.source_sha256, rec))

    scored.sort(key=lambda item: (-item[0], item[1], item[2], item[3]))
    slots = [
        {
            "slot_index": idx,
            "record_id": rec.record_id,
            "manifold": rec.manifold,
            "coords": [round(c, 12) for c in rec.coords],
            "distance": round(dist, 12),
            "proximity": round(1.0 / (1.0 + dist), 12),
            "weight": round(float(rec.weight), 12),
            "score": round(score, 12),
            "summary": rec.summary[:MAX_SUMMARY_CHARS],
            "source_sha256": rec.source_sha256,
        }
        for idx, (score, dist, _rid, _sha, rec) in enumerate(scored[:budget_slots])
    ]
    capsule: dict[str, Any] = {
        "schema": CAPSULE_SCHEMA,
        "query_manifold": query_manifold,
        "query_coords": [round(c, 12) for c in q_coords],
        "budget_slots": budget_slots,
        "slot_count": len(slots),
        "slots": slots,
    }
    capsule["capsule_sha256"] = compute_capsule_sha256(capsule)
    return capsule


def _provenance_result(
    verdict: str, hash_valid: bool, checked: int, mismatches: list[str], missing: list[str], reason: str
) -> dict[str, Any]:
    return {
        "schema": PROVENANCE_SCHEMA,
        "verdict": verdict,
        "capsule_hash_valid": hash_valid,
        "checked_slots": checked,
        "mismatches": mismatches,
        "missing": missing,
        "reason": reason,
    }


def verify_capsule_provenance(
    capsule: Mapping[str, Any], source_hashes: Mapping[str, str]
) -> dict[str, Any]:
    """Verify capsule digest and every slot's source_sha256 against known source hashes."""
    if not isinstance(capsule, Mapping) or capsule.get("schema") != CAPSULE_SCHEMA:
        return _provenance_result(VERDICT_UNVERIFIABLE, False, 0, [], [], "malformed capsule or schema")
    declared = capsule.get("capsule_sha256")
    try:
        hash_valid = isinstance(declared, str) and compute_capsule_sha256(capsule) == declared
    except (TypeError, ValueError):
        hash_valid = False
    slots = capsule.get("slots")
    if not isinstance(slots, list):
        return _provenance_result(VERDICT_UNVERIFIABLE, hash_valid, 0, [], [], "capsule slots missing or invalid")

    mismatches: list[str] = []
    missing: list[str] = []
    for slot in slots:
        if not isinstance(slot, Mapping):
            mismatches.append("<malformed-slot>")
            continue
        rid = str(slot.get("record_id", ""))
        slot_sha = str(slot.get("source_sha256", "")).lower()
        expected = source_hashes.get(rid) if isinstance(source_hashes, Mapping) else None
        if expected is None:
            missing.append(rid)
        elif not _is_sha256_hex(slot_sha) or slot_sha != str(expected).lower():
            mismatches.append(rid)

    if not hash_valid or mismatches:
        return _provenance_result(
            VERDICT_DRIFT, hash_valid, len(slots), mismatches, missing,
            "capsule digest or slot provenance hash drifted from source",
        )
    if missing or not slots:
        msg = "one or more slots lack a known source hash" if missing else "capsule has zero slots to verify"
        return _provenance_result(VERDICT_UNVERIFIABLE, hash_valid, len(slots), mismatches, missing, msg)
    return _provenance_result(
        VERDICT_MATCH, hash_valid, len(slots), mismatches, missing,
        f"all {len(slots)} capsule slots matched source hashes",
    )
