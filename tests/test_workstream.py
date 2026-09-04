"""Workstream composition: what a parent inherits from the children under it.

A receipt per artifact is not enough once artifacts depend on each other. These
tests pin the properties that decide whether the top of a proof stack means
anything:

  1. DERIVED, NOT ASSERTED. A node cannot report verified because its own check
     passed. It reports verified when its own check passed and everything under
     it is settled, and blocked otherwise.
  2. REFUTATION WINS. A refuted node is refuted whatever holds it up, so a
     withdrawn lemma is never disguised by a healthy dependency.
  3. ASSUMPTIONS COMPOSE AND ARE DISCLOSED. An assumption satisfies its parent
     the way an axiom satisfies a Lean proof, and it is named in the footprint
     rather than erased.
  4. IDENTITY WITNESSES THE SUBTREE. Editing a lemma statement, or moving the
     environment a lemma was checked in, moves the identity of the goal above it.
  5. does_not_prove IS DERIVED AND NON-EMPTY. It is computed from what settled
     and cannot be authored by whoever wants the record to read well.
"""
import pytest

from harness.workstream import (
    BLOCKED, PENDING, REFUTED, SCHEMA, UNVERIFIABLE, VERIFIED,
    Obligation, Workstream, WorkstreamError, settle,
)
from harness.workstream_receipt import workstream_receipt

ENV = "lean4:v4.9.0+mathlib:2026-08-01"


def _ob(name, *, check="lean", env=ENV, deps=(), statement=None):
    return Obligation(
        obligation_id=name,
        statement=statement or f"theorem {name} : True := trivial",
        check=check,
        environment=env,
        depends_on=tuple(deps),
    )


def _stack():
    """A goal over two lemmas, one of which rests on a third."""
    return Workstream(
        [
            _ob("base"),
            _ob("lemma_a", deps=("base",)),
            _ob("lemma_b"),
            _ob("goal", deps=("lemma_a", "lemma_b")),
        ],
        goal="goal",
    )


def test_a_green_leaf_under_a_red_one_is_blocked_never_verified():
    settled = settle(_stack(), {"base": "FAIL", "lemma_a": "PASS",
                                "lemma_b": "PASS", "goal": "PASS"})
    assert settled["base"]["standing"] == REFUTED
    assert settled["lemma_a"]["standing"] == BLOCKED
    assert settled["goal"]["standing"] == BLOCKED
    assert "base" in settled["lemma_a"]["reason"]
    # The healthy sibling keeps its own standing. Blocking is inherited along
    # edges, not smeared across the whole graph.
    assert settled["lemma_b"]["standing"] == VERIFIED


def test_refutation_survives_a_healthy_dependency():
    settled = settle(_stack(), {"base": "PASS", "lemma_a": "FAIL",
                                "lemma_b": "PASS", "goal": "PASS"})
    assert settled["lemma_a"]["standing"] == REFUTED
    assert settled["goal"]["standing"] == BLOCKED


def test_an_unfinished_stack_reports_pending_and_blocks_above_it():
    settled = settle(_stack(), {"base": "PASS", "lemma_b": "PASS"})
    assert settled["lemma_a"]["standing"] == PENDING
    assert settled["goal"]["standing"] == BLOCKED


def test_everything_settled_makes_the_goal_verified():
    settled = settle(_stack(), {"base": "PASS", "lemma_a": "PASS",
                                "lemma_b": "PASS", "goal": "PASS"})
    assert settled["goal"]["standing"] == VERIFIED


def test_an_unverifiable_dependency_blocks_rather_than_refutes():
    # A missing toolchain did not refute the lemma. Reporting the parent as
    # refuted would blame the statement for our environment.
    settled = settle(_stack(), {"base": "UNVERIFIABLE", "lemma_a": "PASS",
                                "lemma_b": "PASS", "goal": "PASS"})
    assert settled["base"]["standing"] == UNVERIFIABLE
    assert settled["goal"]["standing"] == BLOCKED
    assert settled["goal"]["standing"] != REFUTED


def test_an_assumption_satisfies_its_parent_and_is_named_in_the_footprint():
    stream = Workstream(
        [
            _ob("reading", check="assumed", env="instrument:unpinned",
                statement="the plate reader reported 0.42 absorbance"),
            _ob("goal", check="arithmetic", deps=("reading",),
                statement='{"value": 0.42, "interval": [0.4, 0.45]}'),
        ],
        goal="goal",
    )
    receipt = workstream_receipt(stream, {"goal": "PASS"})
    assert receipt["goal_standing"] == VERIFIED
    assert receipt["assumption_footprint"] == ["reading"]
    conditional = [line for line in receipt["does_not_prove"] if "conditional" in line]
    assert conditional and "reading" in conditional[0]


def test_an_assumption_cannot_carry_a_check_result():
    stream = Workstream([_ob("a", check="assumed", statement="taken on trust")], goal="a")
    with pytest.raises(WorkstreamError, match="cannot carry a check result"):
        settle(stream, {"a": "PASS"})


def test_identity_folds_in_the_subtree():
    first = _stack()
    edited = Workstream(
        [
            _ob("base", statement="theorem base : True := by trivial"),
            _ob("lemma_a", deps=("base",)),
            _ob("lemma_b"),
            _ob("goal", deps=("lemma_a", "lemma_b")),
        ],
        goal="goal",
    )
    assert first.digests["goal"] != edited.digests["goal"]
    assert first.digests["lemma_b"] == edited.digests["lemma_b"]
    assert first.workstream_id == first.digests["goal"]


def test_moving_the_environment_moves_every_identity_above_it():
    moved = Workstream(
        [
            _ob("base", env="lean4:v4.9.0+mathlib:2026-09-01"),
            _ob("lemma_a", deps=("base",)),
            _ob("lemma_b"),
            _ob("goal", deps=("lemma_a", "lemma_b")),
        ],
        goal="goal",
    )
    assert moved.digests["goal"] != _stack().digests["goal"]


def test_the_receipt_names_every_environment_the_goal_rests_on():
    stream = Workstream(
        [
            _ob("measured", check="instrument", env="mhs:plate-reader-3/cal-2026-08-30",
                statement="absorbance 0.42 at 600nm"),
            _ob("goal", deps=("measured",)),
        ],
        goal="goal",
    )
    receipt = workstream_receipt(stream, {"measured": "PASS", "goal": "PASS"})
    assert receipt["environment_footprint"] == [
        "lean4:v4.9.0+mathlib:2026-08-01", "mhs:plate-reader-3/cal-2026-08-30"]
    assert any("comparable only where the environment matches" in line
               for line in receipt["does_not_prove"])


def test_does_not_prove_is_never_empty_and_counts_what_is_open():
    receipt = workstream_receipt(_stack(), {"base": "PASS"})
    assert receipt["schema"] == SCHEMA
    assert len(receipt["does_not_prove"]) >= 2
    assert any("pending" in line for line in receipt["does_not_prove"])
    assert any("blocked" in line for line in receipt["does_not_prove"])


def test_the_footprints_cover_the_goal_subtree_only():
    stream = Workstream(
        [_ob("goal"), _ob("unrelated", check="assumed", env="elsewhere",
                          statement="a claim nothing above it uses")],
        goal="goal",
    )
    receipt = workstream_receipt(stream, {"goal": "PASS"})
    assert receipt["reached_from_goal"] == ["goal"]
    assert receipt["assumption_footprint"] == []
    assert receipt["environment_footprint"] == [ENV]
    # It is still settled and still reported. Out of the goal's subtree is not
    # out of the record.
    assert "unrelated" in receipt["obligations"]


@pytest.mark.parametrize("obligations, goal, message", [
    ([_ob("a", deps=("b",))], "a", "rests on missing"),
    ([_ob("a"), _ob("a")], "a", "duplicate obligation id"),
    ([_ob("a")], "b", "is not one of the obligations"),
    ([_ob("a", deps=("b",)), _ob("b", deps=("a",))], "a", "dependency cycle"),
])
def test_a_malformed_workstream_is_refused_at_construction(obligations, goal, message):
    with pytest.raises(WorkstreamError, match=message):
        Workstream(obligations, goal=goal)


def test_an_obligation_cannot_rest_on_itself():
    with pytest.raises(WorkstreamError, match="depends on itself"):
        _ob("a", deps=("a",))


def test_an_unknown_check_kind_is_refused():
    with pytest.raises(WorkstreamError, match="check must be one of"):
        _ob("a", check="vibes")


def test_results_naming_an_absent_obligation_are_refused():
    with pytest.raises(WorkstreamError, match="not here"):
        settle(_stack(), {"nonesuch": "PASS"})


def test_an_unknown_verdict_is_refused_rather_than_read_as_a_pass():
    with pytest.raises(WorkstreamError, match="must be one of"):
        settle(_stack(), {"base": "probably"})


def test_a_deep_chain_settles_without_recursion():
    depth = 2000
    chain = [_ob("n0")]
    chain += [_ob(f"n{i}", deps=(f"n{i - 1}",)) for i in range(1, depth)]
    stream = Workstream(chain, goal=f"n{depth - 1}")
    settled = settle(stream, {f"n{i}": "PASS" for i in range(depth)})
    assert settled[f"n{depth - 1}"]["standing"] == VERIFIED
    broken = settle(stream, {**{f"n{i}": "PASS" for i in range(depth)}, "n0": "FAIL"})
    assert broken[f"n{depth - 1}"]["standing"] == BLOCKED
