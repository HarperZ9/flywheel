"""mesh.py — discover the wiring: whose output plugs into whose input.

Given a set of manifests, the mesh computes producer -> consumer EDGES: for every
capability a tool consumes, it finds the tools that emit something satisfying it.
This is the layer MCP tool lists lack: MCP tells an agent that tools exist; the
mesh tells it how their OUTPUTS chain into each other's INPUTS.

An edge is DECLARED, not probed. It forms by matching capability strings the
manifests self-report; plexus never imports, resolves, or runs the tools, so it
cannot confirm the cited module exists or that the outputs truly compose. Every
edge is tagged `evidence="declared"` and carries the module its producer names,
a self-reported citation to follow, not a verified receipt.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .manifest import duplicate_organs


@dataclass(frozen=True)
class Edge:
    producer: str          # organ id
    consumer: str          # organ id
    capability: str        # the consumer's input capability that the producer satisfies
    producer_module: str
    consumer_module: str
    self_loop: bool = False
    evidence: str = "declared"   # "declared": self-reported, never probed by plexus


@dataclass
class Mesh:
    organs: list           # organ ids, sorted
    edges: list            # list[Edge]
    manifests: dict        # organ -> Manifest (deduped, last-writer-wins)
    collisions: list = field(default_factory=list)  # organ ids declared more than once

    def wiring(self) -> dict:
        """capability -> sorted list of (producer, consumer) pairs."""
        out: dict = {}
        for e in self.edges:
            out.setdefault(e.capability, []).append((e.producer, e.consumer))
        return {k: sorted(v) for k, v in sorted(out.items())}

    def producers_of(self, organ: str) -> list:
        """Organs whose output feeds `organ` (its upstream), sorted unique."""
        return sorted({e.producer for e in self.edges
                       if e.consumer == organ and not e.self_loop})

    def consumers_of(self, organ: str) -> list:
        """Organs that consume `organ`'s output (its downstream), sorted unique."""
        return sorted({e.consumer for e in self.edges
                       if e.producer == organ and not e.self_loop})

    def orphans(self) -> dict:
        """Honesty surface: capabilities consumed by someone but emitted by no
        organ in the set (an unmet input), and emitted but never consumed."""
        emitted, consumed = set(), set()
        for m in self.manifests.values():
            for p in m.emits:
                emitted.add(p.capability)
                emitted.update(p.consumable_as)
            for p in m.consumes:
                consumed.add(p.capability)
        return {"unmet_inputs": sorted(consumed - emitted),
                "unconsumed_outputs": sorted(emitted - consumed)}


def discover(manifests: list) -> Mesh:
    """Build the mesh. An edge (A -> B, cap) exists when B consumes capability
    `cap` and A emits a port that satisfies `cap`."""
    mans = {m.organ: m for m in manifests}
    edges = []
    for consumer in manifests:
        for want in consumer.consumes:
            for producer in manifests:
                for emit in producer.emits:
                    if emit.satisfies(want.capability):
                        edges.append(Edge(
                            producer=producer.organ, consumer=consumer.organ,
                            capability=want.capability,
                            producer_module=emit.module, consumer_module=want.module,
                            self_loop=(producer.organ == consumer.organ),
                            evidence="declared"))
    edges.sort(key=lambda e: (e.capability, e.producer, e.consumer))
    return Mesh(organs=sorted(mans), edges=edges, manifests=mans,
                collisions=duplicate_organs(manifests))
