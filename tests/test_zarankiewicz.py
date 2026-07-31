"""Zarankiewicz: the first real construction certificate.

z(m, n; s, t) is the maximum number of edges in an m by n bipartite graph
containing no complete bipartite subgraph K_{s,t}. A candidate submits a witness
graph and claims an edge count. The checker validates two things exactly:

  1. the declared edges are well formed and match the declared count,
  2. no s columns share t common rows (for s=t=2: no two columns share two rows,
     equivalently no four-cycle).

This is the cheapest oracle class in the entire 2026 literature: the check is
milliseconds of integer work, it is exact, and anyone can re-run it offline.
The generator produces instances in parameter space absent from published tables,
which is what makes the memorization control arm meaningful later.
"""
import json

import pytest

from harness.certificates.zarankiewicz import (
    ZarankiewiczOracle, k22_free, edge_count, encode, GeneratorError,
)
from harness.certificates.generators import (
    zarankiewicz_instance, instance_space,
)


def _cert(m, n, edges, claimed=None, s=2, t=2):
    return json.dumps({
        "m": m, "n": n, "s": s, "t": t,
        "edges": [list(e) for e in edges],
        "edge_count": edge_count(edges) if claimed is None else claimed,
    })


# --- the predicate itself -----------------------------------------------------

def test_a_single_four_cycle_is_detected():
    # (0,0) (0,1) (1,0) (1,1) is exactly K_{2,2}.
    assert k22_free(2, 2, [(0, 0), (0, 1), (1, 0), (1, 1)]) is False


def test_three_of_the_four_cycle_edges_are_free():
    assert k22_free(2, 2, [(0, 0), (0, 1), (1, 0)]) is True


def test_the_empty_graph_is_free():
    assert k22_free(5, 5, []) is True


def test_a_star_is_free_however_large():
    # One row joined to every column shares no second row with anything.
    assert k22_free(4, 9, [(0, j) for j in range(9)]) is True


def test_a_known_optimal_projective_plane_incidence_is_free():
    # The Fano plane incidence graph: 7 points, 7 lines, 3 points per line, 21
    # edges, and z(7,7;2,2)=21. Any two lines meet in exactly ONE point, so no
    # four-cycle exists. This is the tightest positive control available.
    lines = [(0, 1, 2), (0, 3, 4), (0, 5, 6), (1, 3, 5),
             (1, 4, 6), (2, 3, 6), (2, 4, 5)]
    edges = [(p, li) for li, pts in enumerate(lines) for p in pts]
    assert len(edges) == 21
    assert k22_free(7, 7, edges) is True


def test_adding_one_edge_to_the_fano_incidence_creates_a_four_cycle():
    lines = [(0, 1, 2), (0, 3, 4), (0, 5, 6), (1, 3, 5),
             (1, 4, 6), (2, 3, 6), (2, 4, 5)]
    edges = [(p, li) for li, pts in enumerate(lines) for p in pts]
    # Any absent edge closes a four-cycle at the extremal graph.
    present = set(edges)
    extra = next((p, li) for p in range(7) for li in range(7)
                 if (p, li) not in present)
    assert k22_free(7, 7, edges + [extra]) is False


# --- the oracle ---------------------------------------------------------------

def test_a_valid_witness_passes_and_reports_its_edge_count():
    o = ZarankiewiczOracle()
    r = o.verify(_cert(4, 9, [(0, j) for j in range(9)]), None)
    assert r.verdict() == "PASS"
    assert r.objective == "9"


def test_a_witness_containing_a_four_cycle_fails():
    o = ZarankiewiczOracle()
    r = o.verify(_cert(2, 2, [(0, 0), (0, 1), (1, 0), (1, 1)]), None)
    assert r.verdict() == "FAIL"
    assert "K_{2,2}" in r.stdout_excerpt or "four" in r.stdout_excerpt.lower()


def test_an_overclaimed_edge_count_fails_even_when_the_graph_is_free():
    # Claiming more edges than you exhibit is the obvious way to game a
    # maximization objective, so it is checked before the predicate.
    o = ZarankiewiczOracle()
    r = o.verify(_cert(4, 9, [(0, j) for j in range(9)], claimed=99), None)
    assert r.verdict() == "FAIL"
    assert "count" in r.stdout_excerpt.lower()


def test_a_duplicate_edge_fails_rather_than_inflating_the_count():
    o = ZarankiewiczOracle()
    r = o.verify(_cert(4, 4, [(0, 0), (0, 0), (0, 1)], claimed=3), None)
    assert r.verdict() == "FAIL"
    assert "duplicate" in r.stdout_excerpt.lower()


def test_an_out_of_range_vertex_index_fails():
    o = ZarankiewiczOracle()
    r = o.verify(_cert(3, 3, [(0, 0), (5, 1)]), None)
    assert r.verdict() == "FAIL"
    assert "range" in r.stdout_excerpt.lower()


def test_a_negative_index_fails():
    o = ZarankiewiczOracle()
    r = o.verify(_cert(3, 3, [(0, 0), (-1, 1)]), None)
    assert r.verdict() == "FAIL"


def test_a_malformed_edge_fails():
    o = ZarankiewiczOracle()
    r = o.verify(json.dumps({"m": 3, "n": 3, "s": 2, "t": 2,
                             "edges": [[0], [1, 1]], "edge_count": 2}), None)
    assert r.verdict() == "FAIL"


def test_an_oversized_instance_is_unverifiable_not_failed():
    o = ZarankiewiczOracle()
    big = _cert(500, 500, [(0, 0)])
    r = o.verify(big, None)
    assert r.verdict() == "UNVERIFIABLE"
    assert r.unverifiable_reason == "OUT_OF_SCOPE"


def test_an_unsupported_s_t_pair_is_unverifiable_not_failed():
    # The checker implements s=t=2. A different pair is outside what it can
    # dispose, which is a gap in the record and not a candidate error.
    o = ZarankiewiczOracle()
    r = o.verify(_cert(4, 4, [(0, 0)], s=3, t=3), None)
    assert r.verdict() == "UNVERIFIABLE"


def test_coverage_reports_an_exact_fully_enumerated_predicate():
    o = ZarankiewiczOracle()
    r = o.verify(_cert(4, 9, [(0, j) for j in range(9)]), None)
    assert r.coverage["predicate_exact"] is True
    assert r.coverage["search_space_enumerated"] is True
    assert "NOT_PROVES_EXACTNESS" not in r.does_not_prove


def test_the_oracle_never_executes_candidate_code():
    import ast
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent
           / "harness" / "certificates" / "zarankiewicz.py")
    tree = ast.parse(src.read_text(encoding="utf-8"))
    banned = {"subprocess", "socket", "ctypes", "pickle", "importlib", "os"}
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
        elif isinstance(node, ast.Name) and node.id in ("eval", "exec", "compile"):
            found.add(node.id)
    assert not (found & (banned | {"eval", "exec", "compile"})), found


# --- the generator ------------------------------------------------------------

def test_a_generated_instance_is_in_scope_and_well_formed():
    o = ZarankiewiczOracle()
    inst = zarankiewicz_instance(seed=7, difficulty=3)
    r = o.verify(encode(inst["m"], inst["n"], inst["seed_edges"]), None)
    assert r.verdict() in ("PASS", "FAIL")     # a witness, not necessarily good
    assert r.verdict() != "UNVERIFIABLE"


def test_the_generator_is_deterministic_in_its_seed():
    a = zarankiewicz_instance(seed=11, difficulty=2)
    b = zarankiewicz_instance(seed=11, difficulty=2)
    assert a == b


def test_different_seeds_give_different_instances():
    a = zarankiewicz_instance(seed=1, difficulty=2)
    b = zarankiewicz_instance(seed=2, difficulty=2)
    assert (a["m"], a["n"]) != (b["m"], b["n"]) or a["seed_edges"] != b["seed_edges"]


def test_difficulty_raises_the_instance_size_monotonically():
    sizes = [zarankiewicz_instance(seed=5, difficulty=d)["m"]
             * zarankiewicz_instance(seed=5, difficulty=d)["n"]
             for d in range(1, 6)]
    assert sizes == sorted(sizes)
    assert sizes[0] < sizes[-1]


def test_generated_instances_avoid_published_table_parameters():
    # The published z(m,n;2,2) tables cover small square cases. Generating there
    # would make a memorization control arm meaningless, so the space excludes
    # them and says so.
    for seed in range(40):
        inst = zarankiewicz_instance(seed=seed, difficulty=3)
        assert (inst["m"], inst["n"]) not in instance_space()["excluded_pairs"]


def test_an_unknown_difficulty_is_refused_rather_than_clamped():
    with pytest.raises(GeneratorError):
        zarankiewicz_instance(seed=1, difficulty=0)
    with pytest.raises(GeneratorError):
        zarankiewicz_instance(seed=1, difficulty=99)


def test_instance_space_declares_what_it_excludes_and_why():
    space = instance_space()
    assert space["excluded_pairs"]
    assert "reason" in space
    assert "published" in space["reason"].lower()
