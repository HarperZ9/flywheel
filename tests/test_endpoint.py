"""The preregistered endpoints, computed against fakes.

No oracle, no pool on disk, no GPU. That is the point: section 4 of the frozen
preregistration says every arm is a pure function of the cache so a stranger can
recompute the analysis on a laptop, and a module that needed a real checker to
be tested would not have that property.

The load-bearing tests are the three that could each hide a wrong answer:
a body whose verdict moves between rung contexts MUST be a disagreement, a body
that appears under two instances MUST NOT be, and an empty union MUST NOT report
the endpoint as met.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.endpoint import (                                       # noqa: E402
    EndpointError, FOUR_WAY, PRIMARY_ENDPOINT, body_digest,
    excluded_tasks, primary_endpoint, secondary_per_rung, union_of_bodies)

RUNGS = ["r1", "r2", "r3"]


def _slot(sha, i=0):
    return {"slot": i, "seed": i, "temperature": 0, "candidate_sha256": sha,
            "error": None}


def _pool(entries, bodies):
    return {"schema": "flywheel.candidate-pool/v1", "entries": entries,
            "bodies": bodies}


def _one_body_everywhere(text="cert-A"):
    sha = body_digest(text)
    doc = _pool([{"task_id": "t0", "slots": [_slot(sha)]}], {sha: text})
    return sha, {r: doc for r in RUNGS}


def _submit(verdict="PASS", attribution="CANDIDATE", well_formed=True,
            verdict_digest=None, subject_digest=None):
    def submit(body, task_id, rung):
        return {
            "verdict": verdict, "attribution": attribution,
            "well_formed": well_formed,
            "verdict_digest": (verdict_digest(body, task_id, rung)
                               if callable(verdict_digest)
                               else f"vd:{body_digest(body)}:{verdict}"),
            "subject_digest": (subject_digest(body, task_id, rung)
                               if callable(subject_digest)
                               else f"sd:{body_digest(body)}:{task_id}"),
        }
    return submit


# --- the union --------------------------------------------------------------

def test_the_union_is_a_set_across_rungs():
    sha, pools = _one_body_everywhere()
    union = union_of_bodies(pools)
    assert list(union) == [sha]
    assert union[sha]["rungs"] == RUNGS
    assert union[sha]["task_ids"] == ["t0"]


def test_recorded_gaps_are_not_bodies():
    """A slot with a null digest is a recorded harness gap. Treating it as a
    body would put an empty string in the union and grade it."""
    doc = _pool([{"task_id": "t0", "slots": [_slot(None)]}], {})
    assert union_of_bodies({"r1": doc}) == {}


def test_a_slot_naming_a_body_the_pool_does_not_carry_is_refused():
    doc = _pool([{"task_id": "t0", "slots": [_slot("sha256:missing")]}], {})
    with pytest.raises(EndpointError):
        union_of_bodies({"r1": doc})


def test_two_bodies_under_one_digest_is_corruption_not_a_tie():
    sha = body_digest("cert-A")
    a = _pool([{"task_id": "t0", "slots": [_slot(sha)]}], {sha: "cert-A"})
    b = _pool([{"task_id": "t0", "slots": [_slot(sha)]}], {sha: "DIFFERENT"})
    with pytest.raises(EndpointError):
        union_of_bodies({"r1": a, "r2": b})


def test_a_task_with_no_candidate_anywhere_is_excluded_and_named():
    doc = _pool([{"task_id": "t0", "slots": [_slot(None), _slot(None, 1)]},
                 {"task_id": "t1", "slots": [_slot(body_digest("x"))]}],
                {body_digest("x"): "x"})
    assert excluded_tasks({"r1": doc}) == {"r1": ["t0"]}


# --- the primary endpoint ---------------------------------------------------

def test_one_body_one_verdict_everywhere_meets_the_endpoint():
    _, pools = _one_body_everywhere()
    out = primary_endpoint(union_of_bodies(pools), RUNGS, _submit())
    assert out["met"] is True
    assert out["n_disagreements"] == 0
    assert out["n_bodies"] == 1
    assert out["rung_contexts"] == RUNGS
    assert out["endpoint"] == PRIMARY_ENDPOINT


def test_a_verdict_that_moves_between_rung_contexts_is_a_disagreement():
    """The whole endpoint. If this passed silently the measurement would be
    incapable of reporting the failure it exists to detect."""
    _, pools = _one_body_everywhere()
    drifting = _submit(verdict_digest=lambda body, task, rung: f"vd:{rung}")
    out = primary_endpoint(union_of_bodies(pools), RUNGS, drifting)
    assert out["met"] is False
    assert out["n_disagreements"] == 1
    assert out["disagreements"][0]["distinct_verdict_digests"] == 3


def test_a_subject_that_moves_between_rung_contexts_is_a_disagreement():
    _, pools = _one_body_everywhere()
    drifting = _submit(subject_digest=lambda body, task, rung: f"sd:{rung}")
    out = primary_endpoint(union_of_bodies(pools), RUNGS, drifting)
    assert out["met"] is False
    assert out["n_disagreements"] == 1


def test_a_body_under_two_instances_is_reported_not_called_a_disagreement():
    """The subject legitimately carries the instance, so such a body HAS two
    lawful subjects. Folding it into disagreements would manufacture a failure
    out of the frozen text's own definition."""
    text = "cert-A"
    sha = body_digest(text)
    doc = _pool([{"task_id": "t0", "slots": [_slot(sha)]},
                 {"task_id": "t1", "slots": [_slot(sha)]}], {sha: text})
    out = primary_endpoint(union_of_bodies({"r1": doc}), ["r1"], _submit())
    assert out["n_disagreements"] == 0
    assert len(out["bodies_under_multiple_instances"]) == 1
    assert out["bodies_under_multiple_instances"][0]["instances"] == ["t0", "t1"]


def test_an_empty_union_does_not_meet_the_endpoint():
    """Zero bodies, zero disagreements. Without the explicit bool(bodies) the
    endpoint would report itself met over nothing at all."""
    out = primary_endpoint({}, RUNGS, _submit())
    assert out["n_bodies"] == 0
    assert out["met"] is False


def test_the_endpoint_refuses_zero_rung_contexts():
    _, pools = _one_body_everywhere()
    with pytest.raises(EndpointError):
        primary_endpoint(union_of_bodies(pools), [], _submit())


def test_the_primary_result_carries_its_own_limits():
    _, pools = _one_body_everywhere()
    out = primary_endpoint(union_of_bodies(pools), RUNGS, _submit())
    joined = " ".join(out["does_not_prove"])
    assert "NOT_PROVES_CORRECTNESS" in joined
    assert "NOT_PROVES_ANY_RUNG_IS_BETTER" in joined


# --- the secondary table ----------------------------------------------------

def test_the_four_way_denominator_keeps_its_zeros():
    """A distribution that omitted its zeros would let a reader mistake an
    absent category for one that was never possible."""
    _, pools = _one_body_everywhere()
    out = secondary_per_rung(pools, _submit(verdict="PASS"))
    row = out["per_rung"]["r1"]
    assert set(row["verdicts"]) == set(FOUR_WAY)
    assert row["verdicts"]["PASS"] == 1 and row["verdicts"]["UNDECIDED"] == 0
    assert row["graded_slots"] == 1 and row["well_formed"] == 1


def test_a_verdict_outside_the_vocabulary_is_refused():
    _, pools = _one_body_everywhere()
    with pytest.raises(EndpointError):
        secondary_per_rung(pools, _submit(verdict="MOSTLY_FINE"))


def test_the_secondary_table_carries_its_confounds_and_takes_no_delta():
    _, pools = _one_body_everywhere()
    out = secondary_per_rung(pools, _submit())
    assert len(out["confounds"]) >= 5
    assert "NOT_PROVES_A_SIZE_TREND" in " ".join(out["does_not_prove"])
    assert "rung id" in out["ordered_by"]
    # Structural, not textual: the prose legitimately says the words "no
    # cross-rung delta", so grepping the rendered dict would flag its own
    # disclaimer. What must not exist is a computed comparison FIELD.
    for rung, row in out["per_rung"].items():
        assert set(row) == {"graded_slots", "well_formed", "verdicts",
                            "attribution"}, f"{rung} grew a field"
        for key in row:
            assert not any(w in key.lower()
                           for w in ("delta", "diff", "versus", "_vs_", "rank"))
