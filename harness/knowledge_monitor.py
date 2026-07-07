"""knowledge_monitor.py — the standing observation layer over the verified base.

wiki.verify() answers the freshness question at a point in time. This is the
layer that watches: hold the last observation, re-verify on each observe(),
and fire subscriptions on verdict TRANSITIONS only. That discipline is the
whole difference between monitoring and noise — a node that was DRIFT last
observation and is DRIFT again has no new information in it, so its
subscription does not re-fire; a node that returns to MATCH (source restored
or re-verified) fires a recovery transition. Unattended pollers that alert on
state rather than state-CHANGE train their operators to ignore them.

Composes, does not absorb: verification stays in wiki.verify (one implementation
of the verdict), sources come from a caller-supplied provider (polling infra —
cron, feeds, webhooks — lives outside), and the query API reads the sealed base
without ever mutating it. Honest scope: this monitors PROVENANCE freshness
(source changed / absent / unconfirmable), not semantic truth of note content.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .wiki import KnowledgeBase, WikiNode, verify

ANY = "*"          # subscription wildcard: any transition on any node


@dataclass
class Transition:
    node_id: str
    frm: str           # previous verdict ("" on the first observation)
    to: str            # current verdict


@dataclass
class KnowledgeMonitor:
    base: KnowledgeBase
    source_provider: Callable[[], dict]      # -> current_sources for wiki.verify
    last: dict = field(default_factory=dict)          # node_id -> last verdict
    observations: int = 0
    _subs: dict = field(default_factory=dict)         # node_id|ANY -> [callbacks]

    # -- observation ----------------------------------------------------------

    def observe(self) -> dict:
        """One observation: re-verify the base against current sources, diff
        against the previous observation, fire subscriptions on transitions.
        Returns the report: current verdict lists + exactly what changed."""
        v = verify(self.base, self.source_provider())
        per_node = v["per_node"]
        transitions = [Transition(nid, self.last.get(nid, ""), verdict)
                       for nid, verdict in per_node.items()
                       if self.last.get(nid, "") != verdict]
        for t in transitions:
            for cb in self._subs.get(t.node_id, []) + self._subs.get(ANY, []):
                cb(t)
        self.last = dict(per_node)
        self.observations += 1
        return {"observation": self.observations,
                "overall": v["overall"],
                "seal_intact": v["seal_intact"],
                "fresh": sorted(k for k, x in per_node.items() if x == "MATCH"),
                "drifted": sorted(v["drifted"]),
                "unverifiable": sorted(v["unverifiable"]),
                "transitions": [(t.node_id, t.frm, t.to) for t in transitions]}

    def subscribe(self, node_id: str, callback: Callable[[Transition], None]) -> None:
        """Fire `callback` when `node_id`'s verdict CHANGES (use ANY for all
        nodes). Fires on transitions only — steady state never re-fires."""
        self._subs.setdefault(node_id, []).append(callback)

    # -- query API (read-only over the sealed base) ---------------------------

    def query_by_concepts(self, concepts: list[str]) -> list[WikiNode]:
        want = set(concepts)
        return [n for n in self.base.nodes if want & set(n.concepts)]

    def query(self, *, kind: str | None = None, tier: str | None = None,
              verdict: str | None = None) -> list[WikiNode]:
        """Filter nodes by kind/tier and, after an observation, by their LAST
        observed verdict (verdict filter before any observation matches nothing
        — unobserved is not fresh)."""
        out = []
        for n in self.base.nodes:
            if kind is not None and n.kind != kind:
                continue
            if tier is not None and n.tier != tier:
                continue
            if verdict is not None and self.last.get(n.id) != verdict:
                continue
            out.append(n)
        return out

    def neighbors(self, node_id: str) -> list[str]:
        """Nodes linked to `node_id` through the DERIVED (shared-concept) links."""
        out = set()
        for a, b, _shared in self.base.links:
            if a == node_id:
                out.add(b)
            elif b == node_id:
                out.add(a)
        return sorted(out)
