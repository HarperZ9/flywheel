"""transitive witness falsifier — compositional criterion-conservation.

The novel property (untouched by the 2026-07-06 arXiv sweep): MATCH is conserved
ONLY along a fully-MATCH dependency path. Each test would FAIL if the closure
were wrong:
  - ancestor drift GAPS its dependents (closure propagates) but NOT independents
    (paraconsistent localization);
  - a node with no receipt can never MATCH (adversarial gate);
  - cycles / dangling grounding collapse to UNVERIFIABLE, never MATCH;
  - when nothing drifts, MATCH is conserved end-to-end.
"""
from harness.transitive_witness import (
    DepNode, transitive_verdicts, frontier_verdict, dependents_of,
    MATCH, DRIFT, UNVERIFIABLE)


def test_ancestor_drift_gaps_dependents_only():
    # A drifts; B and C depend on A; D is independent.
    nodes = [
        DepNode("A", local=DRIFT),
        DepNode("B", local=MATCH, deps=["A"]),
        DepNode("C", local=MATCH, deps=["B"]),   # two hops from A
        DepNode("D", local=MATCH, deps=[]),       # independent
    ]
    v = transitive_verdicts(nodes)
    assert v["A"] == DRIFT                         # own glut, localized
    assert v["B"] == UNVERIFIABLE                  # grounded on a glut -> gap
    assert v["C"] == UNVERIFIABLE                  # propagates two hops
    assert v["D"] == MATCH, "independent node must NOT degrade (localization)"


def test_match_is_conserved_when_nothing_drifts():
    nodes = [
        DepNode("root", local=MATCH),
        DepNode("mid", local=MATCH, deps=["root"]),
        DepNode("leaf", local=MATCH, deps=["mid"]),
    ]
    v = transitive_verdicts(nodes)
    assert all(x == MATCH for x in v.values())
    assert frontier_verdict(nodes) == MATCH


def test_descendant_of_glut_becomes_gap_not_glut():
    # paraconsistent: a descendant grounded on a contradiction is UNVERIFIABLE,
    # NOT itself DRIFT — its own content was never refuted.
    nodes = [DepNode("A", local=DRIFT), DepNode("B", local=MATCH, deps=["A"])]
    assert transitive_verdicts(nodes)["B"] == UNVERIFIABLE


def test_no_receipt_never_matches():
    nodes = [DepNode("x", local=MATCH, has_receipt=False)]
    assert transitive_verdicts(nodes)["x"] == UNVERIFIABLE


def test_local_unverifiable_propagates_as_gap():
    nodes = [
        DepNode("A", local=UNVERIFIABLE),
        DepNode("B", local=MATCH, deps=["A"]),
    ]
    v = transitive_verdicts(nodes)
    assert v["A"] == UNVERIFIABLE and v["B"] == UNVERIFIABLE


def test_cycle_collapses_to_unverifiable():
    nodes = [DepNode("A", local=MATCH, deps=["B"]),
             DepNode("B", local=MATCH, deps=["A"])]
    v = transitive_verdicts(nodes)
    assert v["A"] == UNVERIFIABLE and v["B"] == UNVERIFIABLE


def test_dangling_grounding_is_unverifiable():
    # cites an ancestor that isn't in the DAG -> grounding unconfirmable
    nodes = [DepNode("B", local=MATCH, deps=["ghost"])]
    assert transitive_verdicts(nodes)["B"] == UNVERIFIABLE


def test_dependents_of_is_exactly_the_affected_set():
    nodes = [
        DepNode("A", local=MATCH),
        DepNode("B", local=MATCH, deps=["A"]),
        DepNode("C", local=MATCH, deps=["B"]),
        DepNode("D", local=MATCH, deps=[]),
        DepNode("E", local=MATCH, deps=["D"]),
    ]
    assert dependents_of(nodes, "A") == {"B", "C"}   # D, E provably unaffected


def test_frontier_verdict_severity_order():
    # DRIFT dominates UNVERIFIABLE dominates MATCH
    drift = [DepNode("A", local=DRIFT), DepNode("B", local=MATCH)]
    gap = [DepNode("A", local=UNVERIFIABLE), DepNode("B", local=MATCH)]
    ok = [DepNode("A", local=MATCH), DepNode("B", local=MATCH)]
    assert frontier_verdict(drift) == DRIFT
    assert frontier_verdict(gap) == UNVERIFIABLE
    assert frontier_verdict(ok) == MATCH


def test_empty_dag_is_safe():
    assert transitive_verdicts([]) == {}
    assert frontier_verdict([]) == MATCH


def test_sibling_of_drift_holds_the_line():
    # the sharp localization falsifier: A drifts, B depends on A (gap), but C is a
    # sibling sharing a CLEAN ancestor R — C must stay MATCH.
    nodes = [
        DepNode("R", local=MATCH),
        DepNode("A", local=DRIFT, deps=["R"]),
        DepNode("B", local=MATCH, deps=["A"]),
        DepNode("C", local=MATCH, deps=["R"]),
    ]
    v = transitive_verdicts(nodes)
    assert v["C"] == MATCH, "a sibling on a clean path must survive a cousin's drift"
    assert v["B"] == UNVERIFIABLE and v["A"] == DRIFT and v["R"] == MATCH
