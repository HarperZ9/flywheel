"""Pure verdict rule shared across the proof-packet family.

Faithful to crucible's ``verdict_for``: margin = (tolerance - deviation)/tolerance,
MATCH if margin >= 0 else DRIFT; a None/non-finite/negative deviation or a
non-positive tolerance is UNVERIFIABLE (fail-closed). Stdlib-only, no third-party
dependency, so every domain packet stays self-contained while any real crucible
run re-derives the identical verdict.
"""

from __future__ import annotations

import math

MATCH = "MATCH"
DRIFT = "DRIFT"
UNVERIFIABLE = "UNVERIFIABLE"


def verdict_for_measurement(deviation: float | None, tolerance: float) -> str:
    if deviation is None or not math.isfinite(deviation) or deviation < 0:
        return UNVERIFIABLE
    if tolerance is None or tolerance <= 0:
        return UNVERIFIABLE
    margin = (tolerance - deviation) / tolerance
    return MATCH if margin >= 0 else DRIFT


def combine_overall(statuses: list[str]) -> str:
    """UNVERIFIABLE dominates, then DRIFT; empty reads MATCH (nothing to refute)."""
    if UNVERIFIABLE in statuses:
        return UNVERIFIABLE
    if DRIFT in statuses:
        return DRIFT
    return MATCH
