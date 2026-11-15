"""Grounding falsifiers: the built-in registry must produce the SAME edges its
seed declares (internal consistency of the hardcoded manifests). These do NOT
read flagship source: the built-in manifests are DECLARED citations, re-checked
by no probe here, so a flagship renaming a cited symbol will NOT break them. That
staleness is a known, disclosed limit (see registry.py), not something this suite
can catch.
"""
from plexus.mesh import discover
from plexus.plan import plan_to, route
from plexus.registry import builtin_manifests


def _mesh():
    return discover(builtin_manifests())


def _edge(mesh, producer, consumer, capability):
    return any(e.producer == producer and e.consumer == consumer
               and e.capability == capability for e in mesh.edges)


def test_the_flagships_are_present():
    assert {"gather", "crucible", "forum", "index", "mneme"} <= set(_mesh().organs)
    assert {"learn", "telos", "flywheel-infra"} <= set(_mesh().organs)


def test_real_cross_flagship_edges_form():
    m = _mesh()
    assert _edge(m, "gather", "crucible", "gather.digest/1")          # ecosystem_measure
    assert _edge(m, "gather", "mneme", "gather.items/1")              # mneme.ingest.from_gather
    assert _edge(m, "mneme", "crucible", "crucible.thesis/1")         # compose.to_crucible_thesis
    assert _edge(m, "index", "crucible", "index.verification/1")      # verify_index_verification


def test_flagship_action_envelopes_feed_the_index_spine():
    m = _mesh()
    cap = "project-telos.flagship-action/v1"
    feeders = {e.producer for e in m.edges if e.consumer == "index" and e.capability == cap}
    assert {"gather", "crucible", "forum", "index"} <= feeders          # all peers + self

def test_every_edge_is_declared_with_a_cited_module():
    for e in _mesh().edges:
        assert e.evidence == "declared"                                # plexus probes nothing
        assert e.producer_module and ":" in e.producer_module          # a self-declared pointer to check


def test_plan_to_crucible_pulls_the_upstream_producers():
    plan = plan_to(_mesh(), "crucible")
    assert {"gather", "mneme", "index"} <= set(plan["order"])
    assert "gather" in plan["sources"]                       # gather is a pure source


def test_crucible_feedback_loops_with_index_and_mneme_are_reported_not_hidden():
    # crucible's status envelope feeds index's spine; index's verification feeds
    # crucible's measurement. Its replay template also feeds Mneme, whose replay
    # pack and thesis both feed Crucible. The planner must surface every member.
    plan = plan_to(_mesh(), "crucible")
    assert {"crucible", "index", "mneme"} <= set(plan["cyclic"])


def test_route_gather_to_crucible_is_connected():
    r = route(_mesh(), "gather", "crucible")
    assert r["connected"] and r["hops"] >= 1


def test_orphans_are_honest_about_external_inputs():
    orph = _mesh().orphans()
    # inputs that come from outside the five (human/other systems) are surfaced
    assert "external-agent-trace/1" in orph["unmet_inputs"]       # forum ingests external traces
    assert "conversation-turns/1" in orph["unmet_inputs"]         # mneme ingests raw turns
