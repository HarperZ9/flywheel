"""Tests for the agent loop -- make -> look -> compare -> adjust, grounded and gated."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from coherence_membrane.agent_loop import (
    ADJUST,
    CONVERGED,
    INDETERMINATE,
    AgentLoop,
    BasinReport,
    Goal,
    basin_agreement,
)
from coherence_membrane.observation import Observation, Provenance, Status
from coherence_membrane.organs.raw import RawFrameOrgan
from coherence_membrane.organs.visual import VisualArtifactOrgan


def _mk(subject, identity, phash_hex="0000000000000000"):
    return Observation(
        organ="visual-artifact", subject=subject, summary="observed", status=Status.PASS,
        provenance=Provenance.witness_bytes(subject, b"x", "high"),
        data={"identity_sha256": identity, "perceptual_hash": phash_hex},
    )


# --- look / compare / adjust ----------------------------------------------


def test_look_converged_on_identical():
    goal = Goal.from_observation(_mk("art", "a" * 64, "0000000000000000"))
    p = AgentLoop(goal).look(_mk("art", "a" * 64, "0000000000000000"))
    assert p.disposition == CONVERGED and p.converged
    assert p.drift.verdict == "MATCH"


def test_look_adjust_beyond_tolerance():
    goal = Goal("art", "a" * 64, 0, tolerance=2)
    p = AgentLoop(goal).look(_mk("art", "b" * 64, "000000000000000f"))  # distance 4
    assert p.disposition == ADJUST and not p.converged
    assert p.drift.distance == 4


def test_look_converged_within_tolerance():
    goal = Goal("art", "a" * 64, 0, tolerance=4)
    p = AgentLoop(goal).look(_mk("art", "b" * 64, "000000000000000f"))  # distance 4 <= 4
    assert p.disposition == CONVERGED and p.converged
    assert p.drift.distance == 4


def test_look_indeterminate_when_goal_has_no_fingerprint():
    goal = Goal("art", "g" * 64, None)
    p = AgentLoop(goal).look(_mk("art", "x" * 64, "00ff00ff00ff00ff"))
    assert p.disposition == INDETERMINATE and not p.converged


def test_look_indeterminate_when_nothing_perceivable():
    # RawFrameOrgan returns [] for a non-Frame subject -> nothing to compare
    loop = AgentLoop(Goal("x", "a" * 64, 0), organ=RawFrameOrgan())
    p = loop.look(b"not a frame")
    assert p.disposition == INDETERMINATE


def test_look_perceives_bytes_through_the_organ(make_png):
    png = make_png(8, 8, bytes((i * 5) % 256 for i in range(8 * 8 * 3)))
    goal = Goal.from_observation(VisualArtifactOrgan().observe(png)[0])
    p = AgentLoop(goal).look(png)  # same bytes -> MATCH
    assert p.converged and p.disposition == CONVERGED


def test_goal_from_observation_extracts_fingerprint():
    g = Goal.from_observation(_mk("art", "a" * 64, "00000000000000ff"), tolerance=3)
    assert g.identity_sha256 == "a" * 64 and g.fingerprint == 255 and g.tolerance == 3


def test_proposal_serialisable():
    p = AgentLoop(Goal("art", "a" * 64, 0)).look(_mk("art", "a" * 64))
    d = p.to_dict()
    assert d["disposition"] == CONVERGED
    assert d["drift"]["verdict"] == "MATCH"
    assert "reasons" in d and "iteration" in d


# --- iterate ---------------------------------------------------------------


def test_iterate_drives_to_convergence_and_stops():
    goal_obs = _mk("art", "g" * 64, "0000000000000000")
    loop = AgentLoop(Goal.from_observation(goal_obs))
    far = _mk("art", "x" * 64, "ffffffffffffffff")  # distance 64
    subjects = iter([far, goal_obs, goal_obs])  # third should never be consumed
    proposals = list(loop.iterate(lambda: next(subjects), max_iterations=5))
    assert [p.disposition for p in proposals] == [ADJUST, CONVERGED]
    assert proposals[-1].converged
    assert len(loop.history) == 2  # stopped at convergence, did not consume the third


def test_iterate_respects_max_iterations():
    goal = Goal("art", "g" * 64, 0)  # never reached
    loop = AgentLoop(goal)
    far = _mk("art", "x" * 64, "ffffffffffffffff")
    proposals = list(loop.iterate(lambda: far, max_iterations=3))
    assert len(proposals) == 3
    assert all(p.disposition == ADJUST for p in proposals)


# --- authorize / commit (the gated step) -----------------------------------


def test_authorize_requires_a_result():
    with pytest.raises(ValueError):
        AgentLoop(Goal("art", "a" * 64, 0)).authorize()


def test_commit_reversible_action_flows_free():
    d = AgentLoop(Goal("art", "a" * 64, 0)).commit("draw", "canvas")
    assert d.gated is False and d.decision == "allow"


def test_commit_consequential_without_a_look_is_needs_human():
    d = AgentLoop(Goal("art", "a" * 64, 0)).commit("publish", "site", authorization={})
    assert d.gated is True and d.decision == "needs-human"
    assert "no witnessed look" in d.reasons[0]


def test_defaulted_commit_fails_closed_after_an_unperceivable_look():
    # look(good) then an unperceivable look (RawFrameOrgan returns [] on non-frame
    # bytes) must CLEAR the default, so a defaulted consequential commit fails
    # closed to needs-human rather than silently reusing the stale good obs.
    good = _mk("art", "a" * 64, "00ff00ff00ff00ff")
    loop = AgentLoop(Goal.from_observation(good), organ=RawFrameOrgan())
    loop.look(good)  # perceivable (an Observation is accepted directly)
    assert loop.look(b"not a frame").disposition == INDETERMINATE  # clears _last_obs
    d = loop.commit("publish", "art", authorization={})
    assert d.gated is True and d.decision == "needs-human"


def test_loop_does_not_mutate_input_file(make_png, tmp_path):
    # inertness at the loop boundary: look()/iterate() never write the artifact.
    png = make_png(4, 4, bytes(4 * 4 * 3))
    p = tmp_path / "frame.png"
    p.write_bytes(png)
    before = p.read_bytes()
    goal = Goal.from_observation(VisualArtifactOrgan().observe(png)[0])
    loop = AgentLoop(goal)
    loop.look(p)
    list(loop.iterate(lambda: p, max_iterations=2))
    assert p.read_bytes() == before  # inert: the loop perceives, never mutates


# --- end-to-end with the real write-gate, if available ---------------------


def _proof_surface_src() -> Path:
    return Path(__file__).resolve().parents[2] / "proof-surface" / "src"


def _receipt():
    now = datetime.now(timezone.utc)
    return {
        "authorization_version": "0.1", "receipt_id": "r1", "kind": "authorization-grant",
        "principal": {"id": "operator"}, "agent": {"id": "agent:studio"},
        "intent": "publish a reviewed artifact",
        "scope": {"allowed_actions": ["publish"], "allowed_targets": []},
        "granted_at": (now - timedelta(hours=1)).isoformat(),
        "expires_at": (now + timedelta(hours=1)).isoformat(), "revoked": False,
    }


def _require_proof_surface():
    src = _proof_surface_src()
    if src.exists():
        sys.path.insert(0, str(src))
    pytest.importorskip("proof_surface")


def test_commit_allows_when_authorized_and_matches_baseline():
    _require_proof_surface()
    art = _mk("site/index.html", "a" * 64, "00ff00ff00ff00ff")
    loop = AgentLoop(Goal.from_observation(art))
    assert loop.look(art).converged          # the result is at the goal
    loop.authorize()                          # operator pins this result as the baseline
    d = loop.commit("publish", "site/index.html", authorization=_receipt())
    assert d.gated is True and d.decision == "allow"


def test_commit_denies_a_result_that_drifted_from_authorized():
    """The safety property: a consequential commit of something that does NOT
    match the approved state is denied by the gate, even with a valid grant."""
    _require_proof_surface()
    approved = _mk("site/index.html", "a" * 64, "0000000000000000")
    drifted = _mk("site/index.html", "b" * 64, "000000000000000f")
    loop = AgentLoop(Goal.from_observation(approved))
    loop.authorize(approved)
    d = loop.commit("publish", "site/index.html", observation=drifted, authorization=_receipt())
    assert d.gated is True and d.decision == "deny"


def test_commit_without_authorized_baseline_is_needs_human():
    _require_proof_surface()
    art = _mk("site/index.html", "a" * 64, "00ff00ff00ff00ff")
    loop = AgentLoop(Goal.from_observation(art))
    loop.look(art)  # looked, but never authorized a baseline
    d = loop.commit("publish", "site/index.html", authorization=_receipt())
    assert d.decision == "needs-human"  # no baseline -> UNVERIFIABLE -> needs-human


# --- A2: basin agreement -- witness path-(in)dependence across independent starts ---------

def test_basin_agreement_one_basin_when_identical():
    # two converged runs with the same perceived identity -> one basin -> path-independent.
    r = basin_agreement([_mk("art", "a" * 64), _mk("art", "a" * 64)])
    assert isinstance(r, BasinReport)
    assert r.runs == 2 and r.basins == 1 and r.agree is True


def test_basin_agreement_flags_path_dependence():
    # different identities, perceptual distance 4 > tolerance 0 -> two basins -> NOT ownerless.
    r = basin_agreement([_mk("art", "a" * 64, "0000000000000000"),
                         _mk("art", "b" * 64, "000000000000000f")], tolerance=0)
    assert r.basins == 2 and r.agree is False
    assert any("PATH-DEPENDENT" in s for s in r.reasons)


def test_basin_agreement_within_tolerance_is_one_basin():
    # same distance-4 pair, but tolerance 4 folds them into one basin.
    r = basin_agreement([_mk("art", "a" * 64, "0000000000000000"),
                         _mk("art", "b" * 64, "000000000000000f")], tolerance=4)
    assert r.basins == 1 and r.agree is True


def test_basin_agreement_empty_is_not_vacuous_agreement():
    r = basin_agreement([])
    assert r.runs == 0 and r.agree is False  # nothing witnessed != agreement


def test_converge_multistart_witnesses_agreement():
    goal = Goal.from_observation(_mk("art", "a" * 64))
    loop = AgentLoop(goal)
    makes = [lambda: _mk("art", "a" * 64), lambda: _mk("art", "a" * 64)]
    results, report = loop.converge_multistart(makes, max_iterations=3)
    assert all(o is not None for o in results)
    assert report.runs == 2 and report.agree is True


def test_converge_multistart_marks_non_converging_start():
    goal = Goal("art", "a" * 64, 0)  # tolerance 0; a far, wrong-identity result never converges
    loop = AgentLoop(goal)
    makes = [lambda: _mk("art", "a" * 64),                       # converges (MATCH)
             lambda: _mk("art", "z" * 64, "00ffffffffffffff")]   # never matches -> None
    results, report = loop.converge_multistart(makes, max_iterations=3)
    assert results[0] is not None and results[1] is None
    assert report.runs == 1 and report.agree is True             # only the converged run is basin-counted
