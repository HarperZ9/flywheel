"""Mutation (soundness) test for bottleneck_criterion's disjoint-decider cross-check.

THE SEAM (found by an adversarial audit): bottleneck_criterion re-checks a claimed
minimax spanning structure with `graph_ops.spans()` (union-find) for BOTH load-bearing
connectivity questions -- "is the claimed set spanning?" and "do edges below b
disconnect the graph?". A single connectivity kernel cannot catch its own bug: the
re-checker is not disjoint from its own primitive, so a `spans()`-class bug is a latent
false VERIFIED.

THE FIX (proven here): a SECOND, genuinely independent connectivity decider
(`graph_ops.connects_all`, BFS-reachability, shares no helper with union-find) is
cross-checked against `spans()` on both questions. Agreement -> the existing verdict;
DISAGREEMENT -> UNVERIFIABLE with a `discrepancy` reason -- a CAUGHT bug, never a guess
and never a false VERIFIED.

How this test proves it: inject a one-line bug into ONE decider (monkeypatch the name
the criterion calls) and assert a previously-VERIFIED certificate degrades to
UNVERIFIABLE -- the cross-check catches the planted `spans()`-class bug. A positive test
pins that the unmutated criterion still VERIFIES correct input, so the cross-check did
not just break the verdict for everyone."""
from __future__ import annotations

import coherence_membrane.graph_oracle as go
from coherence_membrane.certificate import Verdict
from coherence_membrane.graph import Graph
from coherence_membrane.graph_oracle import BottleneckClaim, bottleneck_criterion


def _weighted() -> Graph:
    # x-y(1), y-z(2), x-z(5): the minimax spanning bottleneck is 2.0 (x-y + y-z).
    # Below b=2.0 only x-y(1) survives -> {z} is cut off, so 2.0 IS minimal.
    return Graph(nodes=("x", "y", "z"),
                 edges=(("x", "y"), ("y", "z"), ("x", "z")),
                 weights=((("x", "y"), 1.0), (("y", "z"), 2.0), (("x", "z"), 5.0)))


# The claim that is genuinely VERIFIED against the real, unmutated code.
_GOOD_CLAIM = BottleneckClaim(_weighted(), (("x", "y"), ("y", "z")), 2.0)


# --- baseline: the cross-check does NOT break a correct claim -------------------

def test_positive_correct_bottleneck_still_verified():
    """Unmutated, the disjoint deciders AGREE and a correct claim stays VERIFIED with
    its re-checkable cut witness (the fix is sound, not merely fail-closed)."""
    c = bottleneck_criterion().judge(_GOOD_CLAIM)
    assert c.verdict is Verdict.VERIFIED, dict(c.evidence)
    ev = dict(c.evidence)
    assert ev["bottleneck"] == "2.0"
    assert "cut" in ev and "spanning_edges" in ev  # witness preserved


# --- mutation: a one-line bug in the BFS decider is CAUGHT ----------------------

def test_mutation_in_bfs_decider_caught_on_spanning_question(monkeypatch):
    """Inject a one-line bug into the BFS decider so it MISreports the claimed set as
    not-spanning. Union-find still says spanning -> the two disagree -> the criterion
    returns UNVERIFIABLE (caught), NEVER a false VERIFIED."""
    # one-line bug: a connectivity decider that always answers "not connected".
    monkeypatch.setattr(go, "connects_all", lambda nodes, edges: False)
    c = bottleneck_criterion().judge(_GOOD_CLAIM)
    assert c.verdict is Verdict.UNVERIFIABLE          # caught, not VERIFIED
    assert c.verdict is not Verdict.VERIFIED          # the cardinal invariant
    assert "discrepancy" in dict(c.evidence)


def test_mutation_in_bfs_decider_caught_on_minimality_question(monkeypatch):
    """A subtler bug: the BFS decider is correct on the (true) spanning question but
    wrong on the below-b question (claims sub-bottleneck edges span when they do not).
    Union-find disagrees -> UNVERIFIABLE on the minimality cross-check, not VERIFIED."""
    real = go.connects_all

    def buggy(nodes, edges):
        edges = tuple(edges)
        # correct for the full claimed set (3 hops of the 2-edge spanning tree path),
        # but always "connected" for the smaller below-b set -> a planted minimality bug.
        if len(edges) >= 2:
            return real(nodes, edges)
        return True  # one-line lie: pretend the sub-bottleneck edges already span

    monkeypatch.setattr(go, "connects_all", buggy)
    c = bottleneck_criterion().judge(_GOOD_CLAIM)
    assert c.verdict is Verdict.UNVERIFIABLE
    assert c.verdict is not Verdict.VERIFIED
    ev = dict(c.evidence)
    assert ev.get("question") == "do edges below b disconnect the graph?"


# --- THE audit finding: a `spans()` bug that WAS a false VERIFIED is now caught ---

def test_spans_bug_that_was_a_false_verified_is_now_caught(monkeypatch):
    """The exact gap the audit found, stated as a test. A NON-spanning claim (only
    x-y, leaving z isolated) is truly REFUTED. Plant a one-line `spans()` bug that
    wrongly accepts the 1-edge set as spanning: under the OLD single-kernel re-checker
    (spans() for BOTH connectivity questions) this slipped through as a FALSE VERIFIED.
    The independent BFS decider says 'not spanning' -> the cross-check now degrades to
    UNVERIFIABLE. No false VERIFIED survives a single-kernel bug."""
    g = _weighted()
    non_spanning_claim = BottleneckClaim(g, (("x", "y"),), 1.0)  # z is isolated

    # sanity: against the real, unmutated code this claim is REFUTED, never VERIFIED.
    assert bottleneck_criterion().judge(non_spanning_claim).verdict is Verdict.REFUTED

    real_spans = go.spans

    def buggy_spans(nodes, edges):
        edges = tuple(edges)
        if len(edges) == 1:               # one-line lie: a lone edge "spans"
            return {n: n for n in nodes}
        return real_spans(nodes, edges)

    monkeypatch.setattr(go, "spans", buggy_spans)
    c = bottleneck_criterion().judge(non_spanning_claim)
    assert c.verdict is Verdict.UNVERIFIABLE          # caught by the cross-check
    assert c.verdict is not Verdict.VERIFIED          # NOT the old false VERIFIED
    assert "discrepancy" in dict(c.evidence)


# --- symmetry: a bug in union-find (`spans()`-class) is equally CAUGHT ----------

def test_mutation_in_unionfind_decider_caught(monkeypatch):
    """The disjointness is symmetric: plant the bug in union-find `spans()` instead.
    The independent BFS decider now disagrees -> UNVERIFIABLE. This is the exact
    `spans()`-class bug the original single-kernel re-checker could NOT see."""
    monkeypatch.setattr(go, "spans", lambda nodes, edges: None)  # one-line: never spans
    c = bottleneck_criterion().judge(_GOOD_CLAIM)
    assert c.verdict is Verdict.UNVERIFIABLE
    assert c.verdict is not Verdict.VERIFIED
    assert "discrepancy" in dict(c.evidence)


def test_mutation_in_unionfind_decider_caught_on_minimality(monkeypatch):
    """A union-find bug on the below-b question (reports sub-bottleneck edges as
    spanning) disagrees with BFS -> caught as a minimality discrepancy, not VERIFIED."""
    real = go.spans

    def buggy(nodes, edges):
        edges = tuple(edges)
        if len(edges) >= 2:
            return real(nodes, edges)
        return {n: n for n in nodes}  # one-line lie: truthy "spans" for the below-b set

    monkeypatch.setattr(go, "spans", buggy)
    c = bottleneck_criterion().judge(_GOOD_CLAIM)
    assert c.verdict is Verdict.UNVERIFIABLE
    assert c.verdict is not Verdict.VERIFIED
    assert dict(c.evidence).get("question") == "do edges below b disconnect the graph?"


# --- the cardinal invariant, stated directly -----------------------------------

def test_no_single_decider_bug_yields_a_false_verified():
    """Sweep every one-line single-decider mutation and assert NONE produces VERIFIED:
    a bug confined to one connectivity kernel can only ever degrade to UNVERIFIABLE,
    never slip through as a false VERIFIED."""
    from _pytest.monkeypatch import MonkeyPatch

    mutations = (
        ("connects_all", lambda nodes, edges: False),
        ("connects_all", lambda nodes, edges: True),
        ("spans", lambda nodes, edges: None),
        ("spans", lambda nodes, edges: {n: n for n in nodes}),
    )
    for name, buggy in mutations:
        with MonkeyPatch.context() as mp:
            mp.setattr(go, name, buggy)
            c = bottleneck_criterion().judge(_GOOD_CLAIM)
            assert c.verdict is not Verdict.VERIFIED, (name, dict(c.evidence))
