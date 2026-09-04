"""The bounded reading: which statements a person owes, and when a reading expires.

Two properties carry this module, and both are asserted over generated graphs
rather than one hand-built example.

  1. THE SURFACE IS BOUNDED. It holds the goal, the goal's own dependencies, and
     the assumptions. Adding an obligation that is none of those leaves it
     exactly as it was, which is what makes the reading cost stay flat while the
     stack under it grows to thirty thousand lemmas.
  2. A READING SURVIVES WORK UNDERNEATH IT. Rewriting a proof three levels down
     does not change what a milestone says, so it does not expire the reading of
     that milestone. Editing the milestone statement does.

The second property is worth stating twice, because the workstream digest
deliberately behaves the other way: it folds in the subtree so a swapped lemma
moves the goal's identity. A verdict wants that. A human reading does not, and an
audit that expires on every proof edit is an audit nobody keeps current.
"""
import json
import random

import pytest

from harness.workstream import Obligation, Workstream, WorkstreamError
from harness.workstream_audit import (
    AUDITED, STALE, UNAUDITED, audit_surface, recorded_audits, statement_digest,
)

ENV = "lean4:v4.9.0+mathlib:2026-08-01"


def _ob(name, *, check="lean", deps=(), statement=None, env=ENV):
    return Obligation(
        obligation_id=name,
        statement=statement or f"theorem {name} : True := trivial",
        check=check,
        environment=env,
        depends_on=tuple(deps),
    )


def _graph(rng, size):
    """A random DAG whose last node is the goal and rests on something."""
    nodes = []
    for index in range(size):
        deps = sorted(rng.sample(range(index), rng.randint(0, min(index, 3))))
        if index == size - 1 and not deps:
            deps = [index - 1]
        nodes.append(_ob(
            f"n{index}",
            check=rng.choice(["lean", "lean", "arithmetic", "assumed"]),
            deps=tuple(f"n{ref}" for ref in deps),
        ))
    return nodes


def _expected(nodes, goal):
    """The membership rule, written out independently of the implementation."""
    by_id = {node.obligation_id: node for node in nodes}
    reached = set(Workstream(nodes, goal=goal).reachable())
    direct = set(by_id[goal].depends_on)
    return {name for name in reached
            if name == goal or name in direct or by_id[name].check == "assumed"}


def test_the_surface_is_the_goal_its_dependencies_and_the_assumptions():
    rng = random.Random(20260904)
    for trial in range(60):
        nodes = _graph(rng, rng.randint(2, 14))
        goal = nodes[-1].obligation_id
        surface = audit_surface(Workstream(nodes, goal=goal))
        assert set(surface["surface"]) == _expected(nodes, goal), trial


def test_adding_a_delegated_obligation_leaves_the_surface_unchanged():
    # The bound is a property, not a hope. This is the assertion the module
    # docstring promises: work that lands under an existing lemma is delegated,
    # so a stack can grow without growing what a person has to read.
    rng = random.Random(717)
    for trial in range(60):
        nodes = _graph(rng, rng.randint(3, 12))
        goal = nodes[-1].obligation_id
        before = audit_surface(Workstream(nodes, goal=goal))
        reached = [name for name in Workstream(nodes, goal=goal).reachable()
                   if name != goal]
        if not reached:
            continue
        under = rng.choice(reached)
        grown = [_ob("extra", check="lean")]
        for node in nodes:
            grown.append(
                _ob(node.obligation_id, check=node.check,
                    statement=node.statement, env=node.environment,
                    deps=node.depends_on + ("extra",))
                if node.obligation_id == under else node)
        after = audit_surface(Workstream(grown, goal=goal))
        assert after["surface"] == before["surface"], trial
        # The new obligation is under the goal, and it is still not read.
        assert after["counts"]["reached"] == before["counts"]["reached"] + 1, trial
        assert after["counts"]["delegated"] == before["counts"]["delegated"] + 1, trial


def test_a_lemma_many_proofs_rest_on_is_still_delegated():
    # Reuse is the mechanism a shared corpus runs on, so if fan-in pulled a
    # statement onto the surface the reading cost would rise as the corpus
    # matured. A kernel-accepted lemma carries the goal however often it is used.
    shared = _ob("shared")
    users = [_ob(f"user{index}", deps=("shared",)) for index in range(5)]
    goal = _ob("goal", deps=tuple(node.obligation_id for node in users))
    surface = audit_surface(Workstream([shared, *users, goal], goal="goal"))
    assert "shared" not in surface["surface"]
    assert set(surface["surface"]) == {"goal", *[node.obligation_id for node in users]}


def test_an_obligation_the_goal_does_not_rest_on_is_not_read():
    stream = Workstream([_ob("used"),
                         _ob("orphan", check="assumed",
                             statement="carried, and nothing reaches it"),
                         _ob("goal", deps=("used",))], goal="goal")
    surface = audit_surface(stream)
    assert set(surface["surface"]) == {"goal", "used"}
    assert surface["surface"]["used"]["reasons"] == [
        "a direct dependency of the goal, so it structures the claim"]


def test_a_proof_rewritten_below_a_milestone_does_not_expire_its_reading():
    def build(deep_statement):
        return Workstream([_ob("deep", statement=deep_statement),
                           _ob("mid", deps=("deep",)),
                           _ob("goal", deps=("mid",))], goal="goal")

    before = build("theorem deep : True := trivial")
    after = build("theorem deep : 1 = 1 := rfl")
    pin = statement_digest(before.nodes["goal"])
    # The workstream identity moves, because a verdict is about the whole stack.
    assert before.workstream_id != after.workstream_id
    # The reading does not, because the milestone still says what it said.
    assert statement_digest(after.nodes["goal"]) == pin
    surface = audit_surface(after, {"goal": pin})
    assert surface["surface"]["goal"]["state"] == AUDITED
    assert not surface["stale"]


@pytest.mark.parametrize("field, value", [
    ("statement", "theorem goal : 2 = 2 := rfl"),
    ("check", "arithmetic"),
    ("env", "lean4:v4.33.1"),
])
def test_editing_what_was_read_expires_the_reading(field, value):
    # The environment counts as part of the reading. A person who read a
    # milestone pinned to one Mathlib revision did not read it under another.
    pin = statement_digest(_ob("goal"))
    edited = _ob("goal", **{field: value})
    surface = audit_surface(Workstream([edited], goal="goal"), {"goal": pin})
    assert surface["surface"]["goal"]["state"] == STALE
    assert surface["stale"] == ["goal"]
    assert any("changed after they were read" in line
               for line in surface["does_not_prove"])


def test_an_unread_statement_says_so_rather_than_reading_as_delegated():
    surface = audit_surface(Workstream([_ob("goal")], goal="goal"))
    assert surface["surface"]["goal"]["state"] == UNAUDITED
    assert surface["unaudited"] == ["goal"]
    assert surface["counts"] == {"reached": 1, "surface": 1, "delegated": 0,
                                 "audited": 0, "stale": 0, "unaudited": 1}


def test_the_caveat_is_never_empty_and_says_what_a_reading_is_not():
    surface = audit_surface(Workstream([_ob("goal")], goal="goal"),
                            {"goal": statement_digest(_ob("goal"))})
    assert surface["counts"]["audited"] == 1
    lines = surface["does_not_prove"]
    assert lines
    # Nothing here compares a statement against the paper it came from, and a
    # record that let a reader forget that would be the whole failure mode.
    assert any("nothing here compares a statement to its source" in line
               for line in lines)
    assert any("says nothing about the obligations beneath it" in line
               for line in lines)


def test_a_reading_recorded_against_something_that_is_not_an_obligation_is_refused():
    with pytest.raises(WorkstreamError, match="carries a reading but is not an obligation"):
        audit_surface(Workstream([_ob("goal")], goal="goal"), {"ghost": "0" * 64})


def test_readings_are_read_off_a_declaration_and_a_declaration_may_carry_none():
    document = {"goal": "goal", "obligations": [
        {"id": "goal", "check": "lean", "environment": ENV,
         "statement": "theorem goal : True := trivial", "audited": "a" * 64}]}
    assert recorded_audits(json.dumps(document)) == {"goal": "a" * 64}
    del document["obligations"][0]["audited"]
    assert recorded_audits(json.dumps(document)) == {}


@pytest.mark.parametrize("value", ["", "abc", "a" * 63, 64])
def test_a_pin_that_is_not_a_statement_digest_is_refused(value):
    document = {"goal": "goal", "obligations": [
        {"id": "goal", "check": "lean", "environment": ENV,
         "statement": "theorem goal : True := trivial", "audited": value}]}
    with pytest.raises(WorkstreamError, match="64-character statement digest"):
        recorded_audits(json.dumps(document))


def test_a_declaration_that_is_not_a_declaration_is_refused():
    with pytest.raises(WorkstreamError, match="a goal string and an obligations list"):
        recorded_audits(json.dumps({"obligations": "all of them"}))
