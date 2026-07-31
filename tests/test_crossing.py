"""The rectilinear crossing family: exact counts over the integers.

The ground truth here is derived rather than looked up, which is the property
that got this family ranked first. K_n drawn on the parabola (i, i^2) is in
convex position with no three points collinear, every 4-subset of a convex point
set has exactly one crossing pairing, and in a complete graph both diagonals are
always edges. So the count is exactly C(n,4) at any size, with no published table
anywhere in the chain and therefore nothing for a model to have memorised.
"""
import json
from itertools import combinations
from math import comb

import pytest

from harness.certificates.crossing import (
    CrossingError, CrossingOracle, count_crossings, general_position,
    normalize_edges, orient, segments_cross,
)
from harness.certificates.crossing_generator import (
    DIFFICULTY_BANDS, GENERATOR_ID, convex_drawing, crossing_instance,
    instance_space,
)
from harness.certificates.crossing_independent import (
    IndependentCrossingOracle, convex_hull_4, count_crossings_by_quadruples,
    differential_orient, orient3,
)
from harness.certificates.independent import AgreementError, cross_check
from harness.certificates.zarankiewicz import GeneratorError


def complete_edges(n):
    return [[u, v] for u in range(n) for v in range(u + 1, n)]


def cert(n, edges, coords, crossings):
    return json.dumps({"n": n, "edges": edges, "coords": coords,
                       "crossings": crossings})


@pytest.fixture(params=[CrossingOracle, IndependentCrossingOracle])
def oracle(request):
    return request.param()


# --- the derived ground truth -----------------------------------------------

@pytest.mark.parametrize("n", range(4, 12))
def test_complete_graph_on_a_parabola_has_exactly_n_choose_4_crossings(oracle, n):
    coords = convex_drawing(n)
    r = oracle.verify(cert(n, complete_edges(n), coords, comb(n, 4)))
    assert r.verdict() == "PASS", r.stdout_excerpt


@pytest.mark.parametrize("n", [5, 7, 9])
def test_off_by_one_on_that_count_is_refused(oracle, n):
    coords = convex_drawing(n)
    for wrong in (comb(n, 4) - 1, comb(n, 4) + 1):
        r = oracle.verify(cert(n, complete_edges(n), coords, wrong))
        assert r.verdict() == "FAIL"


def test_a_path_drawn_on_a_convex_curve_has_no_crossings(oracle):
    """Edges sharing an endpoint meet AT the vertex, which is not interior to
    either segment, so consecutive path edges must not count."""
    n = 8
    edges = [[i, i + 1] for i in range(n - 1)]
    r = oracle.verify(cert(n, edges, convex_drawing(n), 0))
    assert r.verdict() == "PASS"


# --- the two algorithms are genuinely different ------------------------------

def test_the_two_counters_agree_over_pseudorandom_point_sets():
    """The cross-check that matters: straddle tests over edge pairs against
    convex position over vertex quadruples, on drawings neither was tuned for."""
    state = 12345
    for trial in range(40):
        pts, seen = [], set()
        n = 6 + trial % 5
        while len(pts) < n:
            state = (1664525 * state + 1013904223) & 0xFFFFFFFF
            p = (state % 97, (state >> 8) % 97)
            if p not in seen:
                seen.add(p)
                pts.append(p)
        ok, _ = general_position(pts)
        if not ok:
            continue
        edges = normalize_edges(
            [e for i, e in enumerate(complete_edges(n)) if (i + trial) % 3])
        assert count_crossings(pts, edges) == count_crossings_by_quadruples(pts, edges)


def test_the_orientation_primitives_agree_but_are_not_the_same_expression():
    import inspect
    assert inspect.getsource(orient) != inspect.getsource(orient3)
    pts = [(0, 0), (5, 1), (2, 9), (-3, 4), (7, -6), (1, 1)]
    assert differential_orient(pts) == (True, None)


def test_a_mistyped_primitive_would_be_caught(monkeypatch):
    """The one failure a cross-check is otherwise blind to: a shared primitive
    wrong in both checkers. It is caught only because the primitive is written
    twice."""
    import harness.certificates.crossing_independent as ci
    monkeypatch.setattr(ci, "orient3", lambda a, b, c: -ci.orient(a, b, c))
    agree, where = ci.differential_orient([(0, 0), (4, 1), (1, 5)])
    assert agree is False and where is not None


def test_a_disagreeing_primitive_is_a_harness_error_not_a_candidate_failure(
        monkeypatch):
    import harness.certificates.crossing_independent as ci
    monkeypatch.setattr(ci, "orient3", lambda a, b, c: -ci.orient(a, b, c))
    with pytest.raises(AgreementError):
        ci.IndependentCrossingOracle().check(
            {"n": 4, "edges": complete_edges(4), "coords": convex_drawing(4),
             "crossings": 1})


def test_convex_hull_of_four_separates_convex_from_contained():
    assert len(convex_hull_4([(0, 0), (10, 0), (10, 10), (0, 10)])) == 4
    assert len(convex_hull_4([(0, 0), (10, 0), (5, 10), (5, 3)])) == 3


# --- general position is the candidate's responsibility ----------------------

def test_a_collinear_drawing_is_the_candidates_error(oracle):
    coords = [[0, 0], [1, 1], [2, 2], [5, 0]]          # first three collinear
    r = oracle.verify(cert(4, complete_edges(4), coords, 1))
    assert r.verdict() == "FAIL"
    assert "degenerate" in r.stdout_excerpt
    assert r.attribution == "CANDIDATE"


def test_two_vertices_at_the_same_point_are_refused(oracle):
    coords = [[0, 0], [0, 0], [3, 1], [1, 4]]
    r = oracle.verify(cert(4, complete_edges(4), coords, 1))
    assert r.verdict() == "FAIL" and "share the point" in r.stdout_excerpt


# --- structural refusals ------------------------------------------------------

@pytest.mark.parametrize("bad,why", [
    ({"n": 4, "edges": [[0, 1]], "coords": [[0, 0]], "crossings": 0}, "coords"),
    ({"n": 3, "edges": [[0, 1]], "coords": [[0, 0]] * 3, "crossings": 0}, "n="),
    ({"n": 4, "edges": [[0, 9]], "coords": convex_drawing(4), "crossings": 0},
     "outside"),
    ({"n": 4, "edges": [[0, 1]], "coords": convex_drawing(4), "crossings": -1},
     "crossings"),
])
def test_malformed_certificates_are_refused(oracle, bad, why):
    r = oracle.verify(json.dumps(bad))
    assert r.verdict() == "FAIL"
    assert why in r.stdout_excerpt


def test_a_boolean_coordinate_is_not_an_integer(oracle):
    """bool subclasses int in Python, so True would silently read as 1. This is
    the same defect that was found in the Zarankiewicz checker."""
    coords = [[True, 0], [3, 1], [1, 4], [6, 6]]
    r = oracle.verify(cert(4, complete_edges(4), coords, 1))
    assert r.verdict() == "FAIL"


def test_a_float_coordinate_is_refused(oracle):
    """Exactness is the gate this family was selected for passing."""
    coords = [[0.5, 0], [3, 1], [1, 4], [6, 6]]
    r = oracle.verify(cert(4, complete_edges(4), coords, 1))
    assert r.verdict() == "FAIL"


def test_a_self_loop_is_refused():
    with pytest.raises(CrossingError):
        normalize_edges([[2, 2]])


def test_duplicate_edges_normalize_to_one():
    assert normalize_edges([[1, 0], [0, 1], [0, 1]]) == [(0, 1)]


# --- instance binding ---------------------------------------------------------

def test_a_drawing_of_a_different_graph_does_not_answer_the_instance(oracle):
    n = 6
    asked = {"n": n, "edges": complete_edges(n)}
    fewer = complete_edges(n)[:-3]
    r = oracle.verify(cert(n, fewer, convex_drawing(n), count_crossings(
        [tuple(p) for p in convex_drawing(n)], normalize_edges(fewer))), asked)
    assert r.verdict() == "FAIL"
    assert "does not answer the instance" in r.stdout_excerpt


def test_the_same_graph_in_another_edge_order_still_binds(oracle):
    n = 5
    shuffled = [list(reversed(e)) for e in reversed(complete_edges(n))]
    asked = {"n": n, "edges": shuffled}
    r = oracle.verify(cert(n, complete_edges(n), convex_drawing(n), comb(n, 4)),
                      asked)
    assert r.verdict() == "PASS"
    assert r.coverage["instance_bound"] is True


# --- the generator ------------------------------------------------------------

@pytest.mark.parametrize("difficulty", sorted(DIFFICULTY_BANDS))
def test_every_generated_instance_is_non_planar(difficulty):
    for seed in range(6):
        inst = crossing_instance(seed=seed, difficulty=difficulty)
        n, m = inst["n"], len(inst["edges"])
        assert m > 3 * n - 6, (difficulty, seed, n, m)
        assert inst["euler_lower_bound"] > 0


@pytest.mark.parametrize("difficulty", sorted(DIFFICULTY_BANDS))
def test_no_generated_instance_is_a_complete_graph(difficulty):
    """Complete graphs have published rectilinear crossing numbers."""
    for seed in range(8):
        inst = crossing_instance(seed=seed, difficulty=difficulty)
        n = inst["n"]
        assert len(inst["edges"]) < n * (n - 1) // 2


def test_generation_is_deterministic_in_the_seed():
    a = crossing_instance(seed=99, difficulty=3)
    b = crossing_instance(seed=99, difficulty=3)
    assert a == b
    assert a != crossing_instance(seed=100, difficulty=3)


def test_an_unknown_difficulty_is_refused_not_clamped():
    with pytest.raises(GeneratorError, match="Not clamped"):
        crossing_instance(seed=1, difficulty=99)


def test_generated_instances_are_connected():
    inst = crossing_instance(seed=4, difficulty=2)
    n, adj = inst["n"], {i: set() for i in range(inst["n"])}
    for u, v in inst["edges"]:
        adj[u].add(v)
        adj[v].add(u)
    seen, stack = {0}, [0]
    while stack:
        for w in adj[stack.pop()]:
            if w not in seen:
                seen.add(w)
                stack.append(w)
    assert len(seen) == n


def test_the_instance_space_is_declarable():
    space = instance_space()
    assert space["generator_id"] == GENERATOR_ID
    assert sorted(space["difficulties"]) == sorted(DIFFICULTY_BANDS)


# --- end to end ----------------------------------------------------------------

def test_a_generated_instance_can_be_answered_and_cross_checked():
    inst = crossing_instance(seed=7, difficulty=1)
    n, edges = inst["n"], inst["edges"]
    coords = convex_drawing(n)
    truth = count_crossings([tuple(p) for p in coords], normalize_edges(edges))
    text = cert(n, edges, coords, truth)
    task = {"n": n, "edges": edges}
    r = cross_check(CrossingOracle(), IndependentCrossingOracle(), text, task)
    assert r.verdict() == "PASS"
    assert truth >= inst["euler_lower_bound"]


def test_a_cross_check_needs_two_different_implementations():
    with pytest.raises(AgreementError):
        cross_check(CrossingOracle(), CrossingOracle(),
                    cert(4, complete_edges(4), convex_drawing(4), 1))


def test_the_objective_is_the_crossing_count(oracle):
    n = 6
    r = oracle.verify(cert(n, complete_edges(n), convex_drawing(n), comb(n, 4)))
    assert r.objective == str(comb(n, 4))


def test_a_better_drawing_scores_lower_than_the_convex_one():
    """Gradient exists: the convex drawing is the worst case for a complete
    graph, so a drawing with an interior point must do strictly better."""
    n = 5
    convex = [tuple(p) for p in convex_drawing(n)]
    interior = [(0, 0), (100, 0), (50, 90), (10, 80), (48, 40)]
    edges = normalize_edges(complete_edges(n))
    assert general_position(interior)[0]
    assert count_crossings(interior, edges) < count_crossings(convex, edges)
