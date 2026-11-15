"""perceive() -- the inert read API a model grounds on.

A model never reaches for the world directly.  It calls perceive(), which runs
the registered organs over the given subjects and returns a PerceptionSnapshot:
a bundle of witnessed Observations the model may reason over.  This is the
read-gate.  It performs NO action and grants NO authority -- it only reports what
was witnessed.  Acting on what is perceived goes back out through the write-gate
(see membrane.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .observation import Observation
from .organ import Organ
from .organs.ascii_view import AsciiViewOrgan
from .organs.audio import AudioArtifactOrgan
from .organs.braille import BrailleViewOrgan
from .organs.caption import CaptionOrgan
from .organs.color import ColorQuantizeOrgan
from .organs.contour import ContourViewOrgan
from .organs.raw import RawFrameOrgan
from .organs.region import RegionArtifactOrgan
from .organs.structured import StructuredDataOrgan
from .organs.verifier import PropositionalVerifierOrgan
from .organs.quantity_verifier import QuantityVerifierOrgan
from .organs.distribution_verifier import DistributionVerifierOrgan
from .organs.cross_verifier import CrossCheckVerifierOrgan
from .organs.linarith_verifier import LinearArithmeticVerifierOrgan
from .organs.graph_verifier import GraphVerifierOrgan
from .organs.visual import VisualArtifactOrgan


def default_organs() -> list[Organ]:
    return [VisualArtifactOrgan()]


def all_organs() -> list[Organ]:
    """Every built-in organ. Used for selftest and multimodal perception;
    perceive() defaults to visual-only to avoid redundant identity-only
    observations across modalities. The senses are sight (VisualArtifactOrgan),
    hearing (AudioArtifactOrgan), and reading structured data
    (StructuredDataOrgan); RawFrameOrgan is the same sense as the eye (a
    raw-pixel fast path), included so selftest proves it. Each returns [] or an
    identity-only observation for subjects outside its modality, so listing them
    together adds no false signal."""
    return [
        VisualArtifactOrgan(),
        AudioArtifactOrgan(),
        StructuredDataOrgan(),
        RawFrameOrgan(),
        RegionArtifactOrgan(),
        AsciiViewOrgan(),
        BrailleViewOrgan(),
        ContourViewOrgan(),
        ColorQuantizeOrgan(),
        PropositionalVerifierOrgan(),
        QuantityVerifierOrgan(),
        DistributionVerifierOrgan(),
        CrossCheckVerifierOrgan(),
        LinearArithmeticVerifierOrgan(),
        GraphVerifierOrgan(),
        CaptionOrgan(),
    ]


@dataclass(frozen=True)
class PerceptionSnapshot:
    """An inert, serialisable bundle of what was witnessed at a point in time."""

    observations: list[Observation] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "observations": [o.to_dict() for o in self.observations],
        }

    def by_organ(self, organ_name: str) -> list[Observation]:
        return [o for o in self.observations if o.organ == organ_name]


def perceive(
    subjects: list,
    organs: list[Organ] | None = None,
    *,
    timestamp: str | None = None,
) -> PerceptionSnapshot:
    """Run organs over subjects and collect witnessed observations (inert).

    `subjects` are passed to each organ's observe().  Each organ decides what it
    can perceive about a subject; organs that find nothing simply return [].
    """
    active = organs if organs is not None else default_organs()
    observations: list[Observation] = []
    for organ in active:
        for subject in subjects:
            observations.extend(organ.observe(subject))
    return PerceptionSnapshot(
        observations=observations,
        timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
    )
