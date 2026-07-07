"""second_brain.py — the VERIFIED second brain: the pillars, assembled.

The Obsidian second-brains going around (1,500 dead chats -> 500 notes, "Claude
re-reads every 6h, catches duplicates, surfaces forgotten threads") do one thing
we do not, and skip the one thing that matters: they WRITE to your brain
unattended with ZERO verification. An LLM editing a vault on a cron accumulates
hallucinated notes and silently stale claims, and it cannot tell you which of
1,615 notes went stale.

We already built the verified version of every pillar — this module just composes
them into one surface:
  ingest (feeds) -> curate (scout/intake, receipted) -> build a SEALED wiki
  (wiki) -> REFRESH with a real freshness verdict (MATCH/DRIFT/UNVERIFIABLE) ->
  WITNESSED write-back that REFUSES a hallucinated note (propose_write).

Honest scope: this beats the competitors on the axis that matters — faithfulness
and provenance — not on UX, mobile, or plugin ecosystem, where Obsidian is mature
and this is a harness. The differentiator is: every note is grounded and every
refresh is a real verdict, not an LLM re-read.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import feeds, intake, wiki
from .wiki import KnowledgeBase, WikiNode


@dataclass
class VerifiedBrain:
    wiki: KnowledgeBase
    catalog: list[dict]
    digest: object                       # IntakeDigest
    n_sources: int = 0


def build_brain(*catalogs: list[dict], feed_id: str = "brain") -> VerifiedBrain:
    """Ingest one or more source catalogs (sessions, scrapes, docs), curate +
    receipt them (intake), and build a SEALED verified wiki. The whole brain is
    content-addressed; nothing lands without provenance."""
    cats = [c for c in catalogs if c]
    catalog = feeds.merge(*cats) if len(cats) > 1 else (cats[0] if cats else [])
    d = intake.digest(catalog, feed_id=feed_id)
    base = wiki.build(catalog)
    return VerifiedBrain(wiki=base, catalog=catalog, digest=d, n_sources=len(catalog))


def refresh(brain: VerifiedBrain, current_sources: dict) -> dict:
    """The competitors' 'check every 6 hours' feature — but as a real FRESHNESS
    VERDICT, not an unverified re-read. Returns which nodes are MATCH / DRIFT /
    UNVERIFIABLE. The question Obsidian structurally cannot answer."""
    v = wiki.verify(brain.wiki, current_sources)
    per = v["per_node"]
    return {"overall": v["overall"], "drifted": v["drifted"],
            "unverifiable": v["unverifiable"],
            "fresh": [nid for nid, verdict in per.items() if verdict == "MATCH"],
            "n_nodes": len(brain.wiki.nodes)}


def write_note(brain: VerifiedBrain, node: WikiNode, current_sources: dict) -> tuple[bool, str]:
    """Witnessed write-back: a note lands ONLY if its provenance is confirmed. A
    hallucinated / ungrounded / drifted note is refused — the guard the unattended
    second-brains lack. On accept the wiki re-seals."""
    return wiki.propose_write(brain.wiki, node, current_sources)


def brain_report(brain: VerifiedBrain) -> str:
    seal = brain.wiki.seal.root_hash[:12] if getattr(brain.wiki, "seal", None) else "?"
    return (f"verified brain: {len(brain.wiki.nodes)} sealed nodes, "
            f"{len(brain.wiki.links)} derived links, root {seal}; "
            f"{brain.n_sources} sources ingested")
