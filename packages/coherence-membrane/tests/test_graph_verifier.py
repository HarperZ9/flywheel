"""Tests for the Graph-plane criteria + GraphVerifierOrgan.

Covers: each criterion's VERIFIED-with-witness and REFUTED/UNVERIFIABLE paths, the
cardinal soundness probes (no input yields a false VERIFIED; over-cap/malformed ->
UNVERIFIABLE, never a crash), determinism, the organ contract ([] on foreign
subject, fail-closed), and the reconcile-EQUIVALENCE test proving each criterion is
a real reconcile (modelled on tests/test_reconcile.py)."""
from __future__ import annotations

from coherence_membrane.certificate import Verdict
from coherence_membrane.graph import Graph
from coherence_membrane.graph_ops import de_bruijn_graph
from coherence_membrane.graph_oracle import (
    BottleneckClaim,
    ClosureClaim,
    ReachabilityClaim,
    bottleneck_criterion,
    closure_certificate,
    reachability_criterion,
)
from coherence_membrane.observation import Status
from coherence_membrane.organs.graph_verifier import GraphVerifierOrgan
from coherence_membrane.reconcile import reconcile


# --- fixtures -----------------------------------------------------------------

def _triangle():
    # a directed 3-cycle a->b->c->a (a real cycle through every node)
    return Graph(nodes=("a", "b", "c"),
                 edges=(("a", "b"), ("b", "c"), ("c", "a")), directed=True)


def _dag():
    return Graph(nodes=("a", "b", "c"), edges=(("a", "b"), ("b", "c")), directed=True)


def _weighted():
    # x-y(1), y-z(2), x-z(5): minimax spanning bottleneck = 2 (use x-y + y-z)
    return Graph(nodes=("x", "y", "z"),
                 edges=(("x", "y"), ("y", "z"), ("x", "z")),
                 weights=((("x", "y"), 1.0), (("y", "z"), 2.0), (("x", "z"), 5.0)))


def _tree():
    return Graph(nodes=("r", "a", "b", "c"),
                 edges=(("r", "a"), ("a", "b"), ("r", "c")), directed=True)


# --- reachability criterion ---------------------------------------------------

def test_reachability_verified_carries_recheckable_cycle():
    c = reachability_criterion().judge(ReachabilityClaim(_triangle(), "a", expect_cycle=True))
    assert c.verdict is Verdict.VERIFIED
    assert c.oracle == "graph-reachability-debruijn-v1"
    ev = dict(c.evidence)
    cycle = ev["cycle"].split("->")
    # the witness is re-checkable: first==last, and every hop a real edge
    g = _triangle()
    assert cycle[0] == cycle[-1] == "a"
    assert all(g.has_edge(u, v) for u, v in zip(cycle, cycle[1:]))


def test_reachability_refuted_when_no_cycle_but_claimed():
    c = reachability_criterion().judge(ReachabilityClaim(_dag(), "a", expect_cycle=True))
    assert c.verdict is Verdict.REFUTED
    assert dict(c.evidence)["found_cycle"] == "False"


def test_reachability_verified_on_proven_absence():
    # expect_cycle=False on a DAG -> VERIFIED (the absence is the proven property)
    c = reachability_criterion().judge(ReachabilityClaim(_dag(), "a", expect_cycle=False))
    assert c.verdict is Verdict.VERIFIED
    assert "closure" in dict(c.evidence)


def test_reachability_over_cap_is_unverifiable():
    big = de_bruijn_graph(("0", "1"), 3)  # 4 nodes, 8 edges
    c = reachability_criterion(max_nodes=2).judge(ReachabilityClaim(big, "00"))
    assert c.verdict is Verdict.UNVERIFIABLE
    assert "over cap" in c.claim or "cap" in dict(c.evidence).get("reason", "")


def test_reachability_unknown_label_node_is_unverifiable():
    c = reachability_criterion().judge(ReachabilityClaim(_triangle(), "zzz"))
    assert c.verdict is Verdict.UNVERIFIABLE


def test_reachability_malformed_claim_is_unverifiable_not_crash():
    assert reachability_criterion().judge("not a claim").verdict is Verdict.UNVERIFIABLE
    assert reachability_criterion().judge(None).verdict is Verdict.UNVERIFIABLE


# --- bottleneck criterion -----------------------------------------------------

def test_bottleneck_verified_with_cut_witness():
    c = bottleneck_criterion().judge(BottleneckClaim(_weighted(), (("x", "y"), ("y", "z")), 2.0))
    assert c.verdict is Verdict.VERIFIED
    assert c.oracle == "graph-bottleneck-mst-v1"
    ev = dict(c.evidence)
    assert "cut" in ev and "spanning_edges" in ev and ev["bottleneck"] == "2.0"


def test_bottleneck_refuted_when_not_minimal():
    # claiming b=5 (the x-z edge) when x-y + y-z already span with max 2 is NOT minimal
    c = bottleneck_criterion().judge(BottleneckClaim(_weighted(), (("x", "z"), ("y", "z")), 5.0))
    assert c.verdict is Verdict.REFUTED


def test_bottleneck_refuted_when_not_spanning():
    g = Graph(nodes=("a", "b", "c"), edges=(("a", "b"),),
              weights=((("a", "b"), 1.0),))
    c = bottleneck_criterion().judge(BottleneckClaim(g, (("a", "b"),), 1.0))
    assert c.verdict is Verdict.REFUTED  # c is unconnected


def test_bottleneck_refuted_on_wrong_value():
    c = bottleneck_criterion().judge(BottleneckClaim(_weighted(), (("x", "y"), ("y", "z")), 1.0))
    assert c.verdict is Verdict.REFUTED  # actual max spanning weight is 2.0, not 1.0


def test_bottleneck_refuted_on_phantom_edge():
    # a claimed spanning edge that is not a real edge must REFUTE (never VERIFIED)
    c = bottleneck_criterion().judge(BottleneckClaim(_weighted(), (("x", "y"), ("y", "ghost")), 2.0))
    assert c.verdict is Verdict.REFUTED


def test_bottleneck_over_cap_unverifiable():
    c = bottleneck_criterion(max_edges=1).judge(
        BottleneckClaim(_weighted(), (("x", "y"), ("y", "z")), 2.0))
    assert c.verdict is Verdict.UNVERIFIABLE


def test_bottleneck_malformed_is_unverifiable():
    assert bottleneck_criterion().judge(42).verdict is Verdict.UNVERIFIABLE


# --- closure certificate ------------------------------------------------------

def test_closure_verified_composes_jump_edges():
    c = closure_certificate().judge(ClosureClaim(_tree(), "r", "r", "b"))
    assert c.verdict is Verdict.VERIFIED
    assert c.oracle == "graph-closure-composed-v1"
    ev = dict(c.evidence)
    assert ev["path"] == "r->a->b"
    # each composed step is recorded as VERIFIED (the composition is re-derivable)
    assert all(v == "verified" for k, v in c.evidence if k.startswith("step:"))


def test_closure_refuted_when_not_reachable():
    # in the tree, c is NOT an ancestor of b -> 'c reaches b' is REFUTED
    c = closure_certificate().judge(ClosureClaim(_tree(), "r", "c", "b"))
    assert c.verdict is Verdict.REFUTED


def test_closure_unverifiable_on_non_tree():
    diamond = Graph(nodes=("r", "a", "b", "d"),
                    edges=(("r", "a"), ("r", "b"), ("a", "d"), ("b", "d")), directed=True)
    c = closure_certificate().judge(ClosureClaim(diamond, "r", "r", "d"))
    assert c.verdict is Verdict.UNVERIFIABLE  # not a tree -> can't certify by ancestors


def test_closure_over_cap_unverifiable():
    c = closure_certificate(max_nodes=1).judge(ClosureClaim(_tree(), "r", "r", "b"))
    assert c.verdict is Verdict.UNVERIFIABLE


def test_closure_malformed_is_unverifiable():
    assert closure_certificate().judge(object()).verdict is Verdict.UNVERIFIABLE


# --- CARDINAL soundness probes: no input yields a FALSE VERIFIED ---------------

def test_no_false_verified_reachability():
    # sweep: an acyclic graph can NEVER produce VERIFIED for expect_cycle=True.
    g = _dag()
    for node in g.nodes:
        c = reachability_criterion().judge(ReachabilityClaim(g, node, expect_cycle=True))
        assert c.verdict is not Verdict.VERIFIED


def test_no_false_verified_bottleneck_under_perturbation():
    # any claimed bottleneck value other than the true minimax (2.0) must NOT VERIFY,
    # and a non-spanning subset must NOT VERIFY -- soundness over completeness.
    g = _weighted()
    spanning = (("x", "y"), ("y", "z"))
    for bad_b in (0.0, 1.0, 1.5, 3.0, 5.0, -1.0):
        c = bottleneck_criterion().judge(BottleneckClaim(g, spanning, bad_b))
        assert c.verdict is not Verdict.VERIFIED, bad_b
    # only the true value verifies
    assert bottleneck_criterion().judge(BottleneckClaim(g, spanning, 2.0)).verdict is Verdict.VERIFIED


def test_no_false_verified_closure_for_non_ancestors():
    g = _tree()
    # for every (src,dst) where src is NOT a proper ancestor of dst, never VERIFIED
    non_reachable = [("b", "a"), ("c", "b"), ("a", "c"), ("b", "c"), ("c", "a")]
    for src, dst in non_reachable:
        c = closure_certificate().judge(ClosureClaim(g, "r", src, dst))
        assert c.verdict is not Verdict.VERIFIED, (src, dst)


# --- determinism --------------------------------------------------------------

def test_determinism_same_claim_same_certificate():
    claim = ReachabilityClaim(_triangle(), "a", expect_cycle=True)
    c1 = reachability_criterion().judge(claim)
    c2 = reachability_criterion().judge(claim)
    assert c1 == c2  # frozen Certificate value-equality -> bit-identical


# --- organ contract -----------------------------------------------------------

def test_organ_foreign_subject_returns_empty():
    org = GraphVerifierOrgan()
    assert org.observe("not a graph claim") == []
    assert org.observe(None) == []
    assert org.observe(42) == []


def test_organ_selftest_passes():
    r = GraphVerifierOrgan().selftest()
    assert r.passed, r.to_dict()
    assert len(r.checks) >= 5


def test_organ_observe_never_raises_on_decided_and_undecided():
    org = GraphVerifierOrgan()
    good = org.observe(ReachabilityClaim(_triangle(), "a", expect_cycle=True))[0]
    assert good.status == Status.PASS and good.data["verdict"] == "verified"
    capped = GraphVerifierOrgan(max_nodes=1).observe(ReachabilityClaim(_triangle(), "a"))[0]
    assert capped.status == Status.UNVERIFIED and capped.data["verdict"] == "unverifiable"


def test_organ_provenance_full_width_digest():
    obs = GraphVerifierOrgan().observe(ReachabilityClaim(_triangle(), "a"))[0]
    assert obs.provenance.digest.startswith("sha256:")
    assert len(obs.provenance.digest) == len("sha256:") + 64


# --- reconcile EQUIVALENCE (the proof it's a real reconcile) -------------------

def test_reconcile_equivalence_reachability():
    # mirrors test_reconcile.py::test_reconcile_is_the_verifier_organ -- the organ IS a
    # reconcile (identity perceive + the reachability criterion): same verdict, same
    # oracle, same witnessed evidence.
    claim = ReachabilityClaim(_triangle(), "a", expect_cycle=True)
    obs = reconcile(claim, criterion=reachability_criterion())
    organ = GraphVerifierOrgan().observe(claim)[0]
    assert obs.status == Status.PASS
    assert obs.data["verdict"] == organ.data["verdict"] == "verified"
    assert obs.data["oracle"] == organ.data["oracle"] == "graph-reachability-debruijn-v1"
    assert obs.data["criterion"] == "graph-reachability"
    assert obs.data["evidence"] == organ.data["evidence"]


def test_reconcile_equivalence_bottleneck():
    claim = BottleneckClaim(_weighted(), (("x", "y"), ("y", "z")), 2.0)
    obs = reconcile(claim, criterion=bottleneck_criterion())
    organ = GraphVerifierOrgan().observe(claim)[0]
    assert obs.data["verdict"] == organ.data["verdict"] == "verified"
    assert obs.data["oracle"] == organ.data["oracle"]
    assert obs.data["evidence"] == organ.data["evidence"]


def test_reconcile_equivalence_closure():
    claim = ClosureClaim(_tree(), "r", "r", "b")
    obs = reconcile(claim, criterion=closure_certificate())
    organ = GraphVerifierOrgan().observe(claim)[0]
    assert obs.data["verdict"] == organ.data["verdict"] == "verified"
    assert obs.data["oracle"] == organ.data["oracle"]
    assert obs.data["evidence"] == organ.data["evidence"]


def test_reconcile_fail_closed_on_graph_criterion():
    # a malformed subject through reconcile degrades to UNVERIFIABLE, never raises.
    obs = reconcile("garbage", criterion=reachability_criterion())
    assert obs.status == Status.UNVERIFIED and obs.data["verdict"] == "unverifiable"
