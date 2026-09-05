"""Falsifiers for the native-UI coverage gate.

The gate exists because a hand audit got this wrong twice: once by counting
the dead `/api/agent` branch as a live route, and once by letting a bare
`/api` reference in the client prefix-match every route and report 100%
coverage. Both failures were silent and both flattered the result.

These hold the properties that prevent a repeat.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import check_ui_coverage as G  # noqa: E402


# A gateway in miniature: `_route_operation` claims /api/agent, and `_post`
# carries a copy of the handler that can therefore never run. The real file no
# longer contains such a branch, so the rule is held against this fixture
# instead. Deleting the last dead branch must not delete the rule that finds
# the next one.
_FIXTURE = '''
class _Handler:
    def _route_operation(self, method):
        path = self.path
        return path == "/api/agent" or path.startswith("/api/operations/")

    def _post(self):
        p = self.path
        if p == "/api/agent":
            return self._run()
        if p == "/api/world":
            return self._world()
'''


def test_a_branch_the_operation_route_claims_is_recorded_as_dead():
    """`_route_operation` returns True before `_gateway_method` calls its
    fallback, so a copy of the handler inside `_post` never executes. The gate
    must know that, because reasoning from such a branch is how effort
    handling sat unreachable for a release."""
    _, dead = G.live_routes(_FIXTURE)
    assert "/api/agent" in dead


def test_the_route_stays_live_even_though_its_post_branch_is_dead():
    """The distinction the gate has to keep: a dead BRANCH is not a dead
    ROUTE. The operation route serves /api/agent, so the capability is real
    and must not vanish from the denominator just because one handler's copy
    of it is unreachable."""
    live, dead = G.live_routes(_FIXTURE)
    assert "/api/agent" in dead
    assert "/api/agent" in live, "the operation route serves it"
    assert "/api/world" in live, "an unclaimed branch is an ordinary route"


def test_the_live_gateway_carries_no_dead_branch():
    """The branch that taught the lesson is gone. Its absence is now a
    property: a new copy of an operation-route handler in `_get` or `_post`
    fails here rather than sitting unreachable for another release."""
    live, dead = G.live_routes()
    assert dead == set(), f"unreachable handler branch(es): {sorted(dead)}"
    assert "/api/agent" in live, "the operation route still serves it"
    assert any(r.startswith("/api/operations") for r in live)


def test_a_bare_api_reference_never_counts_as_a_capability():
    """A base-URL fragment prefix-matches everything. Left in, it manufactured
    100% coverage on a client that referenced almost nothing."""
    assert "/api" not in G.client_routes()


def test_the_client_scan_finds_mid_string_paths():
    """The client writes '$baseUrl/api/world', so the path is not adjacent to
    a quote. A quote-anchored regex missed every call and reported 30%."""
    routes = G.client_routes()
    assert "/api/world" in routes
    assert "/api/lanes" in routes


def test_the_baseline_matches_the_current_gap():
    """A stale baseline is a gate that has stopped measuring. It fails in both
    directions on purpose: a regression and an unclaimed gain both need a
    human to look."""
    live, _ = G.live_routes()
    ui = G.client_routes()
    covered = {r for r in live
               if r in ui or any(u.startswith(r + "/") for u in ui)}
    assert len(live - covered) == G.BASELINE


def test_the_gate_passes_at_its_own_baseline():
    assert G.main() == 0


# A handler that dispatches from a tuple. `_api_strings` read only one side of
# a comparison, so every route served this way was absent from the denominator:
# it could not be counted, and could not appear in the gap the gate freezes.
# Seven live routes were invisible that way, and the reported number was honest
# only because all seven happened to have a surface.
_TUPLE_FIXTURE = '''
class _Handler:
    def _post(self):
        p = self.path
        if p in ("/api/relay/status", "/api/relay/result"):
            return self._relay()
        if p == "/api/plain":
            return self._plain()
'''


def test_a_route_served_from_a_tuple_is_live():
    live, dead = G.live_routes(_TUPLE_FIXTURE)
    assert "/api/relay/status" in live
    assert "/api/relay/result" in live
    # Not a vacuous pass: the ordinary form still works in the same fixture.
    assert "/api/plain" in live
    assert not dead


def test_the_live_gateway_serves_routes_from_tuples():
    """The count the gate divides by. If this drops back to the `==` form only,
    the denominator shrinks and coverage rises without a single new surface."""
    live, _ = G.live_routes()
    assert "/api/typeface/family" in live
    assert "/api/auth/logout" in live


def test_a_client_route_the_engine_does_not_serve_is_a_404():
    """The reverse direction, which nothing else in the repo holds. `flutter
    test` mocks the client so it never dials the engine, and the Python tests
    do not know what the app calls, so a mistyped path ships green from both
    sides and fails at runtime."""
    dangling = G.unserved({"/api/relay/remot"}, {"/api/relay/remote"}, set())
    assert dangling == ["/api/relay/remot"]


def test_a_client_path_under_a_served_family_is_not_dangling():
    assert G.unserved({"/api/operations/run"}, set(), {"/api/operations/"}) == []


def test_a_client_path_under_an_exact_route_is_dangling():
    """Why families are read separately. `live_routes` strips the trailing
    slash, after which an exact route and a prefix family look alike; treating
    every route as a family would let any path below it pass unchecked."""
    assert G.unserved({"/api/lanes/deep"}, {"/api/lanes"}, set()) == ["/api/lanes/deep"]


def test_the_live_client_calls_nothing_the_engine_refuses_to_serve():
    live, _ = G.live_routes()
    assert G.unserved(G.client_routes(), live, G.served_families()) == []
