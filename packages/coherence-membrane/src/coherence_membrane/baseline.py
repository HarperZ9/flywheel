"""Baseline memory -- drift against an authorized baseline, over time.

Frame-to-frame drift answers "did it change since the last tick". Baseline drift
answers the accountability question: "did it change since the operator last
authorized this state". That is EMET's anchor pattern, generalised to perception
and across modalities: a Baseline pins an observation's identity (and perceptual
fingerprint) per subject; later observations are checked against it.

Modality-agnostic: it reads identity, an optional *canonical* (normal-form)
identity, and an optional perceptual fingerprint out of any organ's Observation
(visual `perceptual_hash`, audio `perceptual_audio_hash`, structured-data
`canonical_sha256`), so one baseline can cover frames, sounds, and documents
alike.

The check is a three-rung ladder, strongest first:
  1. byte identity equal           -> MATCH (the strongest statement).
  2. canonical identity equal      -> MATCH (canonically equivalent though the
                                     bytes differ -- e.g. reformatted/reordered
                                     JSON; a canonical difference is real DRIFT).
                                     Structural equivalence, not an understanding
                                     of meaning.
  3. perceptual fingerprint        -> DRIFT, distance-quantified where both
                                     fingerprints exist (visual/audio).
Verdict is the same closed lattice: MATCH / DRIFT / UNVERIFIABLE (no baseline for
this subject, or no identity to compare). Never a silent MATCH on a change.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .observation import Observation
from .phash import DRIFT, MATCH, UNVERIFIABLE, hamming

# Observation.data keys that carry a perceptual fingerprint, in priority order.
_FINGERPRINT_KEYS = ("perceptual_hash", "perceptual_audio_hash")


def _identity(obs: Observation) -> str | None:
    return obs.data.get("identity_sha256")


def _canonical(obs: Observation) -> str | None:
    """A canonical (normal-form) identity that ignores insignificant byte
    differences -- structural, not semantic (currently the structured-data
    organ's canonical_sha256)."""
    return obs.data.get("canonical_sha256")


def _fingerprint(obs: Observation) -> str | None:
    for key in _FINGERPRINT_KEYS:
        value = obs.data.get(key)
        if value:
            return value
    return None


@dataclass(frozen=True)
class BaselineEntry:
    organ: str
    subject: str
    identity_sha256: str
    fingerprint: str | None
    canonical_sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "organ": self.organ,
            "subject": self.subject,
            "identity_sha256": self.identity_sha256,
            "fingerprint": self.fingerprint,
            "canonical_sha256": self.canonical_sha256,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BaselineEntry":
        return cls(
            organ=str(d["organ"]),
            subject=str(d["subject"]),
            identity_sha256=str(d["identity_sha256"]),
            fingerprint=d.get("fingerprint"),
            canonical_sha256=d.get("canonical_sha256"),  # tolerant of older baselines
        )


@dataclass(frozen=True)
class BaselineVerdict:
    verdict: str  # MATCH / DRIFT / UNVERIFIABLE
    distance: int | None
    reason: str


class Baseline:
    """A pinned, authorized baseline of observations, keyed by subject."""

    def __init__(self, entries: dict[str, BaselineEntry] | None = None):
        self.entries: dict[str, BaselineEntry] = dict(entries or {})

    def pin(self, observation: Observation) -> None:
        """Authorize the current observation as the baseline for its subject."""
        identity = _identity(observation)
        if not identity:
            raise ValueError("cannot pin an observation with no identity_sha256")
        self.entries[observation.subject] = BaselineEntry(
            organ=observation.organ,
            subject=observation.subject,
            identity_sha256=identity,
            fingerprint=_fingerprint(observation),
            canonical_sha256=_canonical(observation),
        )

    def check(self, observation: Observation) -> BaselineVerdict:
        """Check an observation against the pinned baseline for its subject."""
        entry = self.entries.get(observation.subject)
        if entry is None:
            return BaselineVerdict(UNVERIFIABLE, None,
                                   "no baseline pinned for this subject")
        if entry.organ != observation.organ:
            # subjects can collide across organs (e.g. the constant "<bytes>");
            # a baseline pinned by one organ must not adjudicate another's.
            return BaselineVerdict(UNVERIFIABLE, None,
                                   "baseline is for a different organ (subject key collision)")
        cur_identity = _identity(observation)
        if not cur_identity:
            return BaselineVerdict(UNVERIFIABLE, None,
                                   "observation has no identity to compare")
        # Rung 1: exact byte identity.
        if cur_identity == entry.identity_sha256:
            return BaselineVerdict(MATCH, 0, "matches the pinned baseline (identity equal)")

        # Rung 2: canonical (normal-form) identity -- bytes differ but the
        # canonical form is unchanged (e.g. reformatted/reordered JSON) is still a
        # MATCH; a canonical difference is a real change, not a perceptual one.
        # Structural equivalence, not an understanding of meaning.
        if entry.canonical_sha256 and (cur_canonical := _canonical(observation)):
            if cur_canonical == entry.canonical_sha256:
                return BaselineVerdict(
                    MATCH, 0,
                    "canonical form equal (normalised bytes match; raw bytes differ)")
            return BaselineVerdict(
                DRIFT, None,
                "canonical form changed from the baseline (normalised content differs)")

        # Rung 3: perceptual fingerprint distance (visual/audio).
        cur_fp = _fingerprint(observation)
        if entry.fingerprint is None or cur_fp is None:
            return BaselineVerdict(
                DRIFT, None,
                "changed from baseline; a perceptual fingerprint is missing so "
                "the magnitude is unquantified",
            )
        distance = hamming(int(entry.fingerprint, 16), int(cur_fp, 16))
        return BaselineVerdict(DRIFT, distance,
                               f"changed from baseline; perceptual distance {distance}/64")

    # --- persistence ------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {"entries": [e.to_dict() for e in self.entries.values()]}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Baseline":
        entries = {}
        for item in d.get("entries", []):
            entry = BaselineEntry.from_dict(item)
            entries[entry.subject] = entry
        return cls(entries)

    def save(self, path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True),
                              encoding="utf-8")

    @classmethod
    def load(cls, path) -> "Baseline":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
