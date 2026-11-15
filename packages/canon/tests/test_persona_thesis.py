"""test_persona_thesis.py -- V3: the persona-as-crucible-thesis drift adapter.

A synthesized-persona-l3 record is a synthesis claim: this text is the faithful
summary of these source memories. canon cannot re-run the synthesis (no model,
that is mneme's L3 extractor), so it cannot judge whether the text is faithful.
What it can measure, model-free from the pool, is whether the persona's basis is
still intact: are the source memories still present, and has none been superseded
by a newer record. canon frames those as falsifiable claims plus model-free
measurements, hands them to the external crucible engine, and reads back its
witnessed MATCH / DRIFT / UNVERIFIABLE verdict. The verdict step stays crucible's
(pure, no model); the measurement step is canon's (structural, no model).

canon is self-contained and stdlib-only, so it cannot import crucible. The
assessor is an injected seam, the same shape V2's writing gate used for the STE
linter: canon owns the thesis payload and the verdict interpretation, the caller
wires the real engine as

    from crucible import Measurement, assess, make_claim, make_thesis
    def assessor(payload):
        claims = [make_claim(c["text"], c["falsification"],
                             tolerance=c["tolerance"]) for c in payload["claims"]]
        th = make_thesis(payload["title"], claims, clock=clock,
                         disposition=payload["disposition"])
        by_id = {cl.id: Measurement(cl.id, cl.sha256, pc["deviation"],
                                    pc["tolerance"], pc["method"], clock())
                 for cl, pc in zip(claims, payload["claims"])}
        a, _ = assess(th, by_id, clock=clock)
        return a.to_dict()

These tests inject a fake assessor that mirrors crucible's honesty ladder
(crucible.verdict.verdict_for + crucible.assess.assess), so no external engine is
imported, yet canon's real measurements drive the real verdict logic end to end.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from canon.persona_thesis import (
    BASIS_TOLERANCE,
    DRIFT,
    MATCH,
    UNVERIFIABLE,
    BasisClaim,
    DriftVerdict,
    PersonaThesis,
    assess_persona,
    persona_thesis,
    thesis_payload,
)
from canon.schema import (
    KIND_EPISODIC_MEMORY,
    KIND_PERSONALITY_BLOCK,
    Provenance,
    Record,
    Temporal,
)

FIXTURE = (Path(__file__).parent / "fixtures" / "records"
           / "synthesized_persona_l3.json")


def _persona(source_ids, *, id="persona-x", scope="global",
             text="A faithful summary.") -> Record:
    prov = Provenance(harness="mneme", source_hash="c" * 64, create_ord=205)
    return Record(kind="synthesized-persona-l3", id=id, scope=scope,
                  data={"layer": "L3", "text": text,
                        "source_ids": list(source_ids)},
                  provenance=prov,
                  temporal=Temporal(valid_until=None, supersedes=None))


def _source(id, *, scope="global", supersedes=None, ord=100) -> Record:
    prov = Provenance(harness="mneme", source_hash="a" * 64, create_ord=ord)
    return Record(kind=KIND_EPISODIC_MEMORY, id=id, scope=scope,
                  data={"layer": "L1", "text": f"memory {id}", "source_ids": []},
                  provenance=prov,
                  temporal=Temporal(valid_until=None, supersedes=supersedes))


def _pool_present(source_ids) -> list[Record]:
    """A pool holding one live source record per id, none superseded."""
    return [_source(sid) for sid in source_ids]


def _ladder_assessor():
    """A fake CrucibleAssessor mirroring crucible.verdict.verdict_for +
    crucible.assess.assess: it applies the honesty ladder to each claim's
    (deviation, tolerance) and returns the assessment counts. It records the
    payload it saw so a test can assert what canon built.

    Ladder (the subset canon exercises): an unmeasured axis (deviation None) is
    UNVERIFIABLE; a non-finite or non-positive tolerance, or a non-finite or
    negative deviation, is UNVERIFIABLE (fail closed); otherwise the margin is
    (tolerance - deviation) / tolerance, MATCH when it is >= 0 else DRIFT.
    """
    import math

    calls: list[dict] = []

    def one(dev, tol) -> str:
        if dev is None:
            return UNVERIFIABLE
        if not math.isfinite(tol) or tol <= 0:
            return UNVERIFIABLE
        if not math.isfinite(dev) or dev < 0:
            return UNVERIFIABLE
        margin = (tol - dev) / tol
        return MATCH if margin >= 0 else DRIFT

    def assessor(payload):
        calls.append(payload)
        counts = {MATCH: 0, DRIFT: 0, UNVERIFIABLE: 0}
        for c in payload["claims"]:
            counts[one(c["deviation"], c["tolerance"])] += 1
        total = len(payload["claims"])
        return {"claims": total, "match": counts[MATCH],
                "drift": counts[DRIFT], "unverifiable": counts[UNVERIFIABLE]}

    assessor.calls = calls  # type: ignore[attr-defined]
    return assessor


def _by_method(thesis: PersonaThesis, method: str) -> BasisClaim:
    for claim in thesis.claims:
        if claim.method == method:
            return claim
    raise AssertionError(f"no basis claim with method {method!r}")


# -- framing --------------------------------------------------------------

def test_persona_thesis_frames_basis_claims():
    record = _persona(["a", "b", "c"], id="persona-operator-0004")
    thesis = persona_thesis(record, pool=_pool_present(["a", "b", "c"]))
    assert isinstance(thesis, PersonaThesis)
    assert thesis.persona_id == "persona-operator-0004"
    methods = {c.method for c in thesis.claims}
    assert {"basis-present", "basis-current"} <= methods
    for claim in thesis.claims:
        assert claim.falsification  # every claim states what would refute it
        assert claim.tolerance == BASIS_TOLERANCE


def test_thesis_refuses_a_non_persona_record():
    prov = Provenance(harness="claude-code", source_hash="a" * 64, create_ord=1)
    block = Record(kind=KIND_PERSONALITY_BLOCK, id="tone", scope="global",
                   data={"title": "Tone", "body": "calm"}, provenance=prov)
    try:
        persona_thesis(block, pool=[])
    except ValueError:
        return
    raise AssertionError("persona_thesis must refuse a non-persona record")


# -- measurement (model-free, from the pool) ------------------------------

def test_basis_present_deviation_counts_missing_sources():
    record = _persona(["a", "b", "c"])
    pool = _pool_present(["a", "b"])  # c is absent
    thesis = persona_thesis(record, pool=pool)
    assert _by_method(thesis, "basis-present").deviation == 1


def test_basis_current_deviation_counts_superseded_sources():
    record = _persona(["a", "b", "c"])
    pool = _pool_present(["a", "b", "c"])
    pool.append(_source("a-v2", supersedes="a"))  # a is superseded by a-v2
    thesis = persona_thesis(record, pool=pool)
    assert _by_method(thesis, "basis-current").deviation == 1


def test_basis_present_deviation_is_zero_when_all_present():
    record = _persona(["a", "b", "c"])
    thesis = persona_thesis(record, pool=_pool_present(["a", "b", "c"]))
    assert _by_method(thesis, "basis-present").deviation == 0
    assert _by_method(thesis, "basis-current").deviation == 0


def test_no_basis_is_unmeasurable():
    record = _persona([])  # a persona that declares no source basis
    thesis = persona_thesis(record, pool=[])
    # An empty basis cannot be measured: deviation is None, an honest null that
    # the ladder reads as UNVERIFIABLE, never as MATCH.
    assert _by_method(thesis, "basis-present").deviation is None


def test_duplicate_source_ids_count_distinct_sources():
    # A basis is a set of source memories: the same id listed twice is one
    # source. Counting an occurrence twice would inflate n and the deviation
    # canon seals into the crucible thesis, so a lone missing (or superseded)
    # source would report a deviation of 2. Both axes count distinct sources.
    absent = persona_thesis(_persona(["a", "a"]), pool=[])
    assert _by_method(absent, "basis-present").deviation == 1  # one source, absent

    pool = _pool_present(["a"])
    pool.append(_source("a-v2", supersedes="a"))
    superseded = persona_thesis(_persona(["a", "a"]), pool=pool)
    assert _by_method(superseded, "basis-current").deviation == 1  # one source, stale

    # Deduping must not regress the all-present case.
    intact = persona_thesis(_persona(["a", "a"]), pool=_pool_present(["a"]))
    assert _by_method(intact, "basis-present").deviation == 0


# -- verdict interpretation ----------------------------------------------

def test_all_sources_present_and_current_is_match():
    record = _persona(["a", "b", "c"])
    verdict = assess_persona(record, pool=_pool_present(["a", "b", "c"]),
                             assess=_ladder_assessor())
    assert isinstance(verdict, DriftVerdict)
    assert verdict.verdict == MATCH
    assert verdict.drift == 0
    assert verdict.unverifiable == 0


def test_a_missing_source_is_drift():
    record = _persona(["a", "b", "c"])
    verdict = assess_persona(record, pool=_pool_present(["a", "b"]),
                             assess=_ladder_assessor())
    assert verdict.verdict == DRIFT
    assert verdict.drift >= 1


def test_a_superseded_source_is_drift():
    record = _persona(["a", "b", "c"])
    pool = _pool_present(["a", "b", "c"])
    pool.append(_source("b-v2", supersedes="b"))
    verdict = assess_persona(record, pool=pool, assess=_ladder_assessor())
    assert verdict.verdict == DRIFT


def test_no_basis_is_unverifiable_not_match():
    record = _persona([])
    verdict = assess_persona(record, pool=[], assess=_ladder_assessor())
    assert verdict.verdict == UNVERIFIABLE
    assert verdict.drift == 0
    assert verdict.unverifiable >= 1


def test_drift_outranks_unverifiable_in_the_headline():
    # A persona with one measurable-and-drifted axis and one unmeasurable axis
    # reads DRIFT: a proven drift is not softened by an honest null elsewhere.
    record = _persona(["a"])  # basis-current measurable; craft a mixed result
    verdict = assess_persona(
        record, pool=_pool_present(["a"]),
        assess=lambda payload: {"claims": 2, "match": 0, "drift": 1,
                                "unverifiable": 1})
    assert verdict.verdict == DRIFT


# -- the injected seam ----------------------------------------------------

def test_thesis_payload_carries_each_claim_measurement():
    record = _persona(["a", "b"])
    thesis = persona_thesis(record, pool=_pool_present(["a"]))  # b missing
    payload = thesis_payload(thesis)
    assert payload["disposition"] == thesis.disposition
    assert isinstance(payload["title"], str) and payload["title"]
    for entry in payload["claims"]:
        assert set(entry) >= {"text", "falsification", "tolerance",
                              "deviation", "method"}
    present = next(e for e in payload["claims"]
                   if e["method"] == "basis-present")
    assert present["deviation"] == 1  # b is missing


def test_assess_persona_reads_counts_directly_fail_closed():
    # canon reads the assessment's drift/unverifiable counts by direct index, the
    # same fail-closed discipline V2's gate used for score["hard"]. An assessor
    # that returns a mapping without those keys is a wiring fault the caller must
    # see, not a silent MATCH.
    record = _persona(["a"])
    try:
        assess_persona(record, pool=_pool_present(["a"]),
                       assess=lambda payload: {"match": 1})  # no drift key
    except KeyError:
        return
    raise AssertionError("assess_persona must raise on a countless assessment")


def test_assessor_receives_the_thesis_payload():
    record = _persona(["a", "b"])
    assessor = _ladder_assessor()
    assess_persona(record, pool=_pool_present(["a", "b"]), assess=assessor)
    assert len(assessor.calls) == 1
    seen = assessor.calls[0]
    assert seen == thesis_payload(persona_thesis(
        record, pool=_pool_present(["a", "b"])))


# -- exit criterion: a real persona-l3 record, read-only and total --------

def test_assess_a_real_persona_record_is_read_only():
    record = Record.from_dict(json.loads(FIXTURE.read_text(encoding="utf-8")))
    pool = _pool_present(record.data["source_ids"]) + [record]
    before = record.to_dict()
    pool_before = copy.deepcopy([r.to_dict() for r in pool])

    verdict = assess_persona(record, pool=pool, assess=_ladder_assessor())

    assert verdict.persona_id == record.id
    assert verdict.verdict == MATCH  # every declared source present and current
    assert record.to_dict() == before  # the record is untouched
    assert [r.to_dict() for r in pool] == pool_before  # the pool is untouched
