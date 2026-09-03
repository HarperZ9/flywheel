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
