"""springloaded fluid-router falsifier — amortize the field, conserve the mass.

Three claims, each a real falsifier: (1) a properly relaxed potential conserves flow
while a self-authored Euclidean heuristic leaks it (same externalization asymmetry);
(2) springloading the field once amortizes across many releases; (3) flow routes
organically around a concave obstacle. Honest bound: the spring is topology-bound —
a blocked cell invalidates it and it must be reloaded (adaptation costs a reload).
"""
from harness.fluid_router import (Grid, springload, euclidean_field, conservation,
                                  springload_amortization, flow_path)

WALL = frozenset({(3, 0), (3, 1), (3, 2), (3, 3)})   # concave wall, gap at y=4
G = Grid(6, 5, sink=(5, 2), blocked=WALL)
SOURCES = [(0, 0), (0, 2), (0, 4), (1, 1), (2, 3)]


def test_relaxed_potential_conserves_all_flow():
    c = conservation(G, springload(G), SOURCES)
    assert c["conserved"] and c["leaked"] == 0 and c["interior_continuity"]


def test_self_authored_euclidean_field_leaks_mass():
    # the plausible straight-line heuristic looks right but loses fluid at local minima
    c = conservation(G, euclidean_field(G), SOURCES)
    assert not c["conserved"] and c["leaked"] > 0


def test_springload_amortizes_across_releases():
    a = springload_amortization(G, SOURCES)
    assert a["amortized"] and a["springloaded_cost"] < a["passive_cost"] and a["speedup"] > 1.0


def test_flow_routes_organically_around_the_obstacle():
    p = flow_path(G, springload(G), (0, 2))
    assert p["reached_sink"]
    assert max(y for _, y in p["path"]) == 4          # used the gap row, routed around
    assert (3, 2) not in p["path"]                    # did not pass through the wall


def test_spring_is_topology_bound_reload_restores_conservation():
    # honest bound: blocking a cell invalidates the field. Block a detour cell that
    # still leaves a route (via the x=5 column); a RELOAD adapts and re-conserves,
    # and the path changes — adaptation costs a reload, it is not free.
    g2 = Grid(6, 5, sink=(5, 2), blocked=WALL | {(4, 3)})
    reloaded = springload(g2)
    assert conservation(g2, reloaded, SOURCES)["conserved"]        # reload re-conserves
    assert (4, 3) not in flow_path(g2, reloaded, (0, 2))["path"]   # rerouted around the block


def test_sealed_region_correctly_reports_a_leak():
    # the criterion is honest in the other direction too: if a block SEALS the only gap,
    # conservation must report the leak, not fake a MATCH
    sealed = Grid(6, 5, sink=(5, 2), blocked=WALL | {(4, 4)})      # seals the only crossing
    assert not conservation(sealed, springload(sealed), SOURCES)["conserved"]
