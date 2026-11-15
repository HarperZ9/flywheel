"""persona_thesis.py -- V3: the persona-as-crucible-thesis drift adapter.

A synthesized-persona-l3 record is a synthesis claim: this text is the faithful
summary of these source memories. canon cannot re-run the synthesis (no model,
that is mneme's L3 extractor), so it cannot judge the text's faithfulness. What
it can measure, model-free from the pool, is whether the persona's basis is still
intact: are the source memories still present, and has none been superseded by a
newer record. canon frames those two axes as falsifiable claims plus model-free
measurements, hands them to the external crucible engine, and reads back its
witnessed MATCH / DRIFT / UNVERIFIABLE verdict. The measurement step is canon's
(structural, no model); the verdict step stays crucible's (pure, no model).

canon is self-contained and stdlib-only, so it cannot import crucible. The
assessor is an injected seam, the same shape V2's writing gate used for the STE
linter (D-38): canon owns the thesis payload and the verdict interpretation, the
caller wires the real engine. A persona verdict is read from crucible's counts by
direct index, so a malformed assessment surfaces as a wiring fault rather than a
silent MATCH, the same fail-closed discipline V2 used for score["hard"] (D-39).
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Callable

from canon.schema import KIND_SYNTHESIZED_PERSONA_L3, Record

# canon's verdict vocabulary, aligned with crucible's (crucible.verdict). canon
# owns these constants because it cannot import crucible; the string values match
# so a reader can cross-reference the two engines.
MATCH = "MATCH"
DRIFT = "DRIFT"
UNVERIFIABLE = "UNVERIFIABLE"

# The strict basis tolerance. A deviation is an integer count of eroded sources,
# so a tolerance of 0.5 means "fewer than one eroded" (integer zero): any erosion
# drifts. crucible rejects a zero or negative tolerance as untrusted, so a
# strict-zero bound is expressed as the largest sub-integer value.
BASIS_TOLERANCE = 0.5

DISPOSITION_PUBLISHABLE = "publishable"

METHOD_BASIS_PRESENT = "basis-present"
METHOD_BASIS_CURRENT = "basis-current"

# The assessment count keys canon reads back, the shape
# crucible.assess(...)[0].to_dict() emits.
MATCH_KEY = "match"
DRIFT_KEY = "drift"
UNVERIFIABLE_KEY = "unverifiable"

# The injected crucible assessor. It takes the thesis payload canon builds and
# returns an assessment mapping carrying int match/drift/unverifiable counts. The
# caller wires the real engine (build crucible claims and measurements from the
# payload, run assess, return the assessment dict); canon never imports crucible.
CrucibleAssessor = Callable[[Mapping], Mapping]


@dataclass(frozen=True, slots=True)
class BasisClaim:
    """One model-free, falsifiable claim about a persona's basis, carrying the
    measurement that decides it. deviation is None when the axis cannot be
    measured (an empty basis), an honest null the verdict ladder reads as
    UNVERIFIABLE, never as MATCH."""

    text: str
    falsification: str
    tolerance: float
    deviation: float | None
    method: str


@dataclass(frozen=True, slots=True)
class PersonaThesis:
    """A synthesized-persona-l3 record framed as a set of falsifiable basis
    claims, ready for the injected crucible assessor."""

    persona_id: str
    title: str
    claims: tuple[BasisClaim, ...]
    disposition: str


@dataclass(frozen=True, slots=True)
class DriftVerdict:
    """canon's headline drift verdict for one persona: MATCH (basis intact),
    DRIFT (basis eroded), or UNVERIFIABLE (basis unmeasurable, an honest null).
    It carries crucible's counts so a caller can read the breakdown."""

    persona_id: str
    verdict: str
    match: int
    drift: int
    unverifiable: int


def _pool_ids(pool: list[Record]) -> set[str]:
    return {r.id for r in pool}


def _superseded_ids(pool: list[Record]) -> set[str]:
    """The ids that some record in the pool supersedes. A source with a newer
    record pointing at it is stale, whatever else is true of the pool."""
    out: set[str] = set()
    for r in pool:
        temporal = r.temporal
        if temporal is not None and temporal.supersedes is not None:
            out.add(temporal.supersedes)
    return out


def persona_thesis(record: Record, *, pool: list[Record]) -> PersonaThesis:
    """Frame a synthesized-persona-l3 record as a crucible thesis of two
    model-free, pool-derived basis claims: every source present, and none
    superseded. A persona with no declared basis yields unmeasurable claims
    (deviation None). Refuses a record of any other kind."""
    if record.kind != KIND_SYNTHESIZED_PERSONA_L3:
        raise ValueError(
            f"persona_thesis frames a {KIND_SYNTHESIZED_PERSONA_L3} record, "
            f"got {record.kind!r}")
    # A basis is a set of sources: dedupe (order-preserving) so a repeated id
    # is one source, not two, in n and in the deviation the thesis seals.
    source_ids = list(dict.fromkeys(record.data.get("source_ids", [])))
    n = len(source_ids)
    if source_ids:
        present = _pool_ids(pool)
        superseded = _superseded_ids(pool)
        missing = float(sum(1 for sid in source_ids if sid not in present))
        stale = float(sum(1 for sid in source_ids
                          if sid in present and sid in superseded))
    else:
        # No basis to measure: both axes are honest nulls (UNVERIFIABLE).
        missing = stale = None  # type: ignore[assignment]
    claims = (
        BasisClaim(
            text=f"all {n} source memories are present in the pool",
            falsification="a declared source memory is absent from the pool",
            tolerance=BASIS_TOLERANCE, deviation=missing,
            method=METHOD_BASIS_PRESENT),
        BasisClaim(
            text=f"no source of the {n} is superseded by a newer record",
            falsification="a declared source is superseded by a newer record",
            tolerance=BASIS_TOLERANCE, deviation=stale,
            method=METHOD_BASIS_CURRENT),
    )
    return PersonaThesis(
        persona_id=record.id, title=f"persona {record.id} basis integrity",
        claims=claims, disposition=DISPOSITION_PUBLISHABLE)


def thesis_payload(thesis: PersonaThesis) -> dict:
    """The crucible thesis payload the injected assessor consumes: the title,
    the disposition, and each claim carrying its measurement. This is the whole
    contract between canon and the wired engine."""
    return {
        "title": thesis.title,
        "disposition": thesis.disposition,
        "claims": [
            {"text": c.text, "falsification": c.falsification,
             "tolerance": c.tolerance, "deviation": c.deviation,
             "method": c.method}
            for c in thesis.claims
        ],
    }


def assess_persona(record: Record, *, pool: list[Record],
                   assess: CrucibleAssessor) -> DriftVerdict:
    """Build the persona's basis thesis, run the injected crucible assessor, and
    interpret its counts into canon's headline verdict. A proven drift outranks
    an honest null: any DRIFT reads DRIFT, else any UNVERIFIABLE reads
    UNVERIFIABLE (fail closed), else MATCH.

    The counts are read by direct index, so an assessor that returns a mapping
    without them is a wiring fault the caller sees, not a silent MATCH.
    """
    thesis = persona_thesis(record, pool=pool)
    result = assess(thesis_payload(thesis))
    drift = result[DRIFT_KEY]
    unverifiable = result[UNVERIFIABLE_KEY]
    if drift > 0:
        verdict = DRIFT
    elif unverifiable > 0:
        verdict = UNVERIFIABLE
    else:
        verdict = MATCH
    return DriftVerdict(
        persona_id=thesis.persona_id, verdict=verdict,
        match=result[MATCH_KEY], drift=drift, unverifiable=unverifiable)
