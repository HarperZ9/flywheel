"""Core falsifiers: manifest model, edge discovery, planning — on a small
synthetic mesh so the logic is checkable independent of the real registry.

Load-bearing: (1) an edge forms exactly when a producer emits a capability the
consumer consumes (incl. consumable_as aliasing); (2) self-loops are marked, not
hidden; (3) plan_to orders producers before the target and names the sources;
(4) route finds a path or reports disconnected; (5) validate reports malformed
manifests without raising.
"""
import pytest

from plexus.manifest import Manifest, Port, validate
from plexus.mesh import discover
from plexus.plan import plan_to, route


def _m(organ, emits=(), consumes=()):
    return Manifest(organ=organ,
                    invoke={"cli": organ},
                    emits=[e if isinstance(e, Port) else Port(*e) for e in emits],
                    consumes=[c if isinstance(c, Port) else Port(*c) for c in consumes])


# a -> b -> c chain, plus b self-loop, plus an alias edge a -> c
A = _m("a", emits=[Port("x/1", module="a.py:x")])
B = _m("b", emits=[Port("y/1", module="b.py:y"), Port("z/1", module="b.py:z")],
       consumes=[Port("x/1", module="b.py:in"), Port("z/1", module="b.py:selfin")])
C = _m("c", consumes=[Port("y/1", module="c.py:in"), Port("w/1", module="c.py:alias")])
A2 = _m("a", emits=[Port("x/1", module="a.py:x"),
                    Port("q/1", module="a.py:q", consumable_as=("w/1",))])


def test_edge_forms_only_on_capability_match():
    mesh = discover([A, B, C])
    pairs = {(e.producer, e.consumer, e.capability) for e in mesh.edges}
    assert ("a", "b", "x/1") in pairs        # a emits x/1, b consumes x/1
    assert ("b", "c", "y/1") in pairs        # b emits y/1, c consumes y/1
    assert not any(e.consumer == "c" and e.capability == "w/1" for e in mesh.edges)  # nobody emits w/1


def test_consumable_as_alias_creates_the_edge():
    mesh = discover([A2, B, C])
    # a emits q/1 declared consumable_as w/1; c consumes w/1 -> a -> c edge
    assert any(e.producer == "a" and e.consumer == "c" and e.capability == "w/1"
               for e in mesh.edges)


def test_self_loop_is_marked_not_dropped():
    mesh = discover([A, B, C])
    selfs = [e for e in mesh.edges if e.self_loop]
    assert selfs and all(e.producer == e.consumer for e in selfs)
    assert ("b", "b") not in [(e.producer, e.consumer) for e in mesh.edges if not e.self_loop]


def test_producers_and_consumers_exclude_self_loops():
    mesh = discover([A, B, C])
    assert mesh.producers_of("c") == ["b"]
    assert mesh.consumers_of("a") == ["b"]
    assert "b" not in mesh.producers_of("b")   # self-loop not counted as upstream


def test_plan_orders_producers_before_target():
    mesh = discover([A, B, C])
    plan = plan_to(mesh, "c")
    assert plan["order"][-1] == "c"            # target last
    assert plan["order"].index("a") < plan["order"].index("b") < plan["order"].index("c")
    assert plan["sources"] == ["a"]            # a is the pure source


def test_route_finds_path_and_reports_disconnected():
    mesh = discover([A, B, C])
    r = route(mesh, "a", "c")
    assert r["connected"] and r["hops"] == 2
    assert [(h["producer"], h["consumer"]) for h in r["path"]] == [("a", "b"), ("b", "c")]
    assert route(mesh, "c", "a")["connected"] is False   # no reverse path


def test_orphans_surface_unmet_and_unconsumed():
    mesh = discover([A, B, C])
    orph = mesh.orphans()
    assert "w/1" in orph["unmet_inputs"]        # c consumes w/1, nobody emits it
    assert "z/1" not in orph["unconsumed_outputs"]  # z/1 is consumed by b (self)


def test_validate_catches_malformed():
    dup = Manifest(organ="d", emits=[Port("k/1"), Port("k/1")])
    assert any("twice" in p for p in validate(dup))
    assert validate(Manifest(organ="")) == ["organ id missing or not a string"] or \
        "organ id missing or not a string" in validate(Manifest(organ=""))


def test_manifest_dict_roundtrip():
    d = A2.to_dict()
    back = Manifest.from_dict(d)
    assert back.organ == "a"
    assert back.emits[1].consumable_as == ("w/1",)
