"""Multimodal composition -- one witnessed instant across senses.

A single perception is one modality. A CompositeObservation bundles several
organs' observations captured at one instant (a frame + its audio + the
structured data behind them) into one witnessed unit with a single, re-derivable
composite identity. compare_composite then reports drift PER MODALITY and overall,
so a model can ground "the scene changed but the audio held" -- not just "something
changed".

This is composition, not signal fusion: each modality is judged independently
(via the existing compare_drift) and the per-modality verdicts are aggregated; it
computes no joint/blended representation. Inert and advisory like every part: it
groups already-witnessed Observations (snapshotting them so the composite identity
cannot drift afterward) and re-derives one digest over their component identities;
it adds no authority.

The overall verdict is the same closed lattice, fail-closed: DRIFT if ANY
component drifted, else UNVERIFIABLE if any component is missing, duplicated,
extra, or unverifiable, else MATCH (every modality confirmed). A missing,
duplicated, or unexpected modality is never a silent MATCH.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .observation import Observation, sha256_hex
from .phash import DRIFT, MATCH, UNVERIFIABLE, compare_drift

# Observation.data keys that carry a perceptual fingerprint (any modality).
_FINGERPRINT_KEYS = ("perceptual_hash", "perceptual_audio_hash")


def _fingerprint_int(obs: Observation) -> int | None:
    """The perceptual fingerprint as an int, accepting either a hex string (the
    organs' on-disk form) or an int (e.g. via JSON interop). bool is rejected."""
    for key in _FINGERPRINT_KEYS:
        value = obs.data.get(key)
        if value is None:
            continue
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            try:
                return int(value, 16)
            except ValueError:
                return None
        return None
    return None


def composite_identity(components: list[Observation]) -> str:
    """A single re-derivable digest over the components' (organ, subject, identity).

    Order-independent (sorted) so the same set of components yields the same
    identity regardless of perception order. Uses a JSON-encoded list of triples
    (not delimiter concatenation) so no field content can shift the framing.
    """
    triples = sorted(
        [c.organ, c.subject, c.data.get("identity_sha256", "")] for c in components
    )
    encoded = json.dumps(triples, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return sha256_hex(encoded)


@dataclass(frozen=True)
class CompositeObservation:
    """Several organs' observations captured at one instant, as one witnessed unit.

    The components are snapshotted (deep-copied) at construction so the composite
    identity is bound to the instant and cannot drift if a caller later mutates the
    list it passed or a component's data -- the same anti-aliasing discipline the
    witness receipt uses.
    """

    components: list[Observation] = field(default_factory=list)
    timestamp: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "components", copy.deepcopy(list(self.components)))

    @property
    def identity(self) -> str:
        return composite_identity(self.components)

    def by_organ(self, organ: str) -> list[Observation]:
        return [c for c in self.components if c.organ == organ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "composite_identity": self.identity,
            "components": [c.to_dict() for c in self.components],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CompositeObservation":
        return cls(
            components=[Observation.from_dict(c) for c in d.get("components", [])],
            timestamp=str(d.get("timestamp", "")),
        )


def perceive_composite(pairs, *, timestamp: str | None = None) -> CompositeObservation:
    """Run several (organ, subject) pairs and bundle their observations as one
    instant. An organ that perceives nothing contributes nothing (it is simply
    absent from the composite -- and a later missing modality reads as UNVERIFIABLE)."""
    components: list[Observation] = []
    for organ, subject in pairs:
        observed = organ.observe(subject)
        if observed:
            components.append(observed[0])
    return CompositeObservation(
        components=components,
        timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
    )


@dataclass(frozen=True)
class ComponentDrift:
    organ: str
    subject: str
    verdict: str
    distance: int | None

    def to_dict(self) -> dict[str, Any]:
        return {"organ": self.organ, "subject": self.subject,
                "verdict": self.verdict, "distance": self.distance}


@dataclass(frozen=True)
class CompositeDriftReport:
    verdict: str  # MATCH / DRIFT / UNVERIFIABLE (overall)
    components: list[ComponentDrift]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"verdict": self.verdict, "reason": self.reason,
                "components": [c.to_dict() for c in self.components]}


def compare_composite(
    baseline: CompositeObservation, current: CompositeObservation
) -> CompositeDriftReport:
    """Compare two composite observations modality-by-modality, fail-closed.

    Components are matched by (organ, subject). A baseline component with no
    matching current component is UNVERIFIABLE (a modality went missing); a
    DUPLICATE (organ, subject) in current is UNVERIFIABLE (ambiguous -- never let
    insertion order decide); a current modality ABSENT from the baseline is
    reported and folds to UNVERIFIABLE (an unexpected sense appeared). Overall:
    DRIFT if any component drifted, else UNVERIFIABLE if any is
    missing/duplicate/extra/unverifiable, else MATCH.
    """
    if not baseline.components:
        return CompositeDriftReport(UNVERIFIABLE, [], "no baseline components to compare")

    # Index current by key, detecting duplicates (ambiguous -> fail closed, not
    # last-write-wins, so the verdict can never depend on component order).
    current_by_key: dict[tuple[str, str], Observation] = {}
    duplicate_keys: set[tuple[str, str]] = set()
    for c in current.components:
        key = (c.organ, c.subject)
        if key in current_by_key:
            duplicate_keys.add(key)
        current_by_key[key] = c

    reports: list[ComponentDrift] = []
    any_drift = False
    any_unverifiable = False
    baseline_keys: set[tuple[str, str]] = set()

    for b in baseline.components:
        key = (b.organ, b.subject)
        baseline_keys.add(key)
        if key in duplicate_keys:
            reports.append(ComponentDrift(b.organ, b.subject, UNVERIFIABLE, None))
            any_unverifiable = True
            continue
        c = current_by_key.get(key)
        if c is None:
            reports.append(ComponentDrift(b.organ, b.subject, UNVERIFIABLE, None))
            any_unverifiable = True
            continue
        dv = compare_drift(
            b.data.get("identity_sha256"), c.data.get("identity_sha256"),
            _fingerprint_int(b), _fingerprint_int(c),
        )
        reports.append(ComponentDrift(b.organ, b.subject, dv.verdict, dv.distance))
        if dv.verdict == DRIFT:
            any_drift = True
        elif dv.verdict == UNVERIFIABLE:
            any_unverifiable = True

    # A modality present in current but absent from the baseline is unexpected:
    # report it and fail closed (never a silent MATCH on an appearing sense).
    seen_extra: set[tuple[str, str]] = set()
    for c in current.components:
        key = (c.organ, c.subject)
        if key not in baseline_keys and key not in seen_extra:
            seen_extra.add(key)
            reports.append(ComponentDrift(c.organ, c.subject, UNVERIFIABLE, None))
            any_unverifiable = True

    if any_drift:
        verdict, reason = DRIFT, "at least one modality drifted"
    elif any_unverifiable:
        verdict, reason = UNVERIFIABLE, "a modality is missing, duplicated, extra, or could not be compared"
    else:
        verdict, reason = MATCH, "every modality matches the baseline"
    return CompositeDriftReport(verdict, reports, reason)
