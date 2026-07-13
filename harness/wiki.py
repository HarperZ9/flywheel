"""wiki.py — the verified second brain. Better than Obsidian on the one axis
Obsidian cannot touch: every node is FAITHFUL (derived, not hand-authored),
carries PROVENANCE, and is RE-CHECKABLE (MATCH / DRIFT / UNVERIFIABLE).

The Obsidian model (and the "feed 1,391 chats into a living wiki" reposts that
chase it): manual markdown + manual [[links]] + a backlink graph + full-text
search. Nothing is verified — a note drifts from its source silently, an
LLM-written summary can hallucinate with no check, and links rot by hand.

This composes two VERIFIED sources into one knowledge graph:
  - CODE nodes from index_wiki: pages derived from the real module graph, each
    content-addressed (sha256), commit-pinned. Not authored -> cannot hallucinate.
  - CORPUS nodes from harness.intake / scout: reposts, chats, articles, docs —
    each scout-classified, carrying a source ref + content hash.

Links are DERIVED, not typed: corpus<->corpus and corpus<->code links come from
shared harness concepts (the scout's word-boundary vocab match), so they are
reproducible, not a human guess. Every node gets a provenance state; verify()
re-checks the whole base against current sources and reports which nodes DRIFTED
(stale knowledge) — the freshness question Obsidian cannot answer.

What this deliberately does NOT claim: Obsidian's manual curation, plugin
ecosystem, and editing UX are real strengths we do not replace. The claim is
narrow and honest — on faithfulness, provenance, and re-checkability, a verified
base beats a pile of unverifiable markdown. `to_markdown()` exports WITH a
provenance header so it interops with Obsidian rather than locking you in.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from . import scout

MIN_SHARED_CONCEPTS = 2   # a derived link needs >= this many shared harness concepts


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


@dataclass
class WikiNode:
    id: str
    kind: str                 # "code" | "corpus"
    title: str
    source_ref: str
    source_hash: str          # content hash at capture ("" -> UNVERIFIABLE)
    concepts: list[str] = field(default_factory=list)
    tier: str = ""            # ACTIONABLE / INSPIRATION / NOISE for corpus; "" for code

    @property
    def provenance(self) -> str:
        return "SEALED" if self.source_hash else "UNVERIFIABLE"

    def to_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "title": self.title,
                "source_ref": self.source_ref, "source_hash": self.source_hash,
                "concepts": self.concepts, "tier": self.tier,
                "provenance": self.provenance}


@dataclass
class WikiSeal:
    root_hash: str
    node_hashes: dict          # node_id -> content hash
    n: int


@dataclass
class KnowledgeBase:
    nodes: list[WikiNode]
    links: list[tuple]         # (a_id, b_id, shared_concepts)
    seal: WikiSeal

    def stale_ok(self) -> list[str]:
        return [n.id for n in self.nodes if n.provenance == "UNVERIFIABLE"]

    def report(self) -> str:
        code = sum(1 for n in self.nodes if n.kind == "code")
        corpus = sum(1 for n in self.nodes if n.kind == "corpus")
        unver = len(self.stale_ok())
        lines = [
            "verified second brain",
            f"  nodes: {len(self.nodes)} ({code} code / {corpus} corpus), "
            f"{len(self.links)} derived links",
            f"  seal root: {self.seal.root_hash}",
            f"  provenance: {len(self.nodes) - unver} sealed, {unver} unverifiable",
        ]
        return "\n".join(lines)


# -- node construction -------------------------------------------------------

def from_corpus(catalog: list[dict], harness_vocab: set[str] | None = None) -> list[WikiNode]:
    """Corpus nodes from a scout catalog (id/text/title/ref). Each node carries
    the harness concepts it names (for derived links) and its scout tier. The
    source_hash is the content hash of the source text at capture time — the
    handle DRIFT is detected against."""
    nodes: list[WikiNode] = []
    for row in catalog:
        assessment = scout.assess(row, harness_vocab)
        text = " ".join(str(row.get(k, "")) for k in ("title", "text", "summary")).strip()
        concepts = scout._hit_terms((" ".join(str(row.get(k, "")) for k in
                                    ("title", "abstract", "summary", "text")).lower()),
                                    harness_vocab or scout.HARNESS_VOCAB)
        rid = str(row.get("id", row.get("ref", "")))
        nodes.append(WikiNode(
            id=f"corpus/{rid}", kind="corpus",
            title=str(row.get("title", rid))[:120],
            source_ref=str(row.get("ref", rid)),
            source_hash=_hash(text) if text else "",
            concepts=concepts, tier=assessment.verdict))
    return nodes


def from_index_wiki(manifest: dict) -> list[WikiNode]:
    """Code nodes from an index_wiki manifest ({pages:[{id, sha256}], commit}).
    The page sha256 IS the source hash — index already content-addressed the page
    against the real module graph, so DRIFT = the code changed under the note."""
    pages = (manifest or {}).get("pages", [])
    nodes: list[WikiNode] = []
    for p in pages:
        pid = str(p.get("id", ""))
        if not pid:
            continue
        # a code page's "concepts" = the harness terms in its id path (module name)
        concepts = scout._hit_terms(pid.replace("/", " ").lower(), scout.HARNESS_VOCAB)
        nodes.append(WikiNode(
            id=f"code/{pid}", kind="code", title=pid,
            source_ref=f"index_wiki:{pid}",
            source_hash=str(p.get("sha256", ""))[:16],
            concepts=concepts, tier=""))
    return nodes


# -- links, sealing, verification -------------------------------------------

def derive_links(nodes: list[WikiNode], min_shared: int = MIN_SHARED_CONCEPTS) -> list[tuple]:
    """Links from SHARED CONCEPTS, not hand-typed. Deterministic: same nodes ->
    same links. (a_id, b_id, sorted_shared_concepts)."""
    links: list[tuple] = []
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            shared = sorted(set(nodes[i].concepts) & set(nodes[j].concepts))
            if len(shared) >= min_shared:
                links.append((nodes[i].id, nodes[j].id, tuple(shared)))
    return links


def _node_content_hash(n: WikiNode) -> str:
    payload = json.dumps({"id": n.id, "kind": n.kind, "source_ref": n.source_ref,
                          "source_hash": n.source_hash,
                          "concepts": sorted(n.concepts), "tier": n.tier},
                         sort_keys=True)
    return _hash(payload)


def seal(nodes: list[WikiNode]) -> WikiSeal:
    """Content-address the base (mirrors chain.py discipline): each node hashed,
    the root hash binds all of them in id order. Tamper any node -> root shifts."""
    node_hashes = {n.id: _node_content_hash(n) for n in nodes}
    ordered = "".join(node_hashes[k] for k in sorted(node_hashes))
    return WikiSeal(root_hash=_hash(ordered) if ordered else "empty",
                    node_hashes=node_hashes, n=len(nodes))


def build(catalog: list[dict], *, index_manifest: dict | None = None,
          harness_vocab: set[str] | None = None) -> KnowledgeBase:
    """Assemble the verified base: corpus nodes (scout-classified) + optional
    code nodes (index_wiki), derived links, sealed manifest."""
    nodes = from_corpus(catalog, harness_vocab)
    if index_manifest:
        nodes = nodes + from_index_wiki(index_manifest)
    links = derive_links(nodes)
    return KnowledgeBase(nodes=nodes, links=links, seal=seal(nodes))


def verify(base: KnowledgeBase, current_sources: dict | None = None) -> dict:
    """Re-check the base. `current_sources` maps node.id -> current material
    (preferred; node.id is unique by construction), or source_ref -> material as
    a convenience ONLY where that ref belongs to exactly one node. Material is
    current content for corpus nodes, current sha256 for code nodes. Per node:
      - no source_hash            -> UNVERIFIABLE
      - ref shared by >1 node and no id-keyed material -> UNVERIFIABLE
        (ambiguous_ref: independent freshness is impossible through a shared
        slot — never guess, and never let node B's snapshot vouch for node A)
      - source unchanged          -> MATCH
      - source changed / missing  -> DRIFT
    Overall: DRIFT if any node drifted; else UNVERIFIABLE if any unverifiable;
    else MATCH. This is the freshness verdict Obsidian cannot produce."""
    current_sources = current_sources or {}
    ref_counts: dict[str, int] = {}
    for n in base.nodes:
        ref_counts[n.source_ref] = ref_counts.get(n.source_ref, 0) + 1
    per_node = {}
    ambiguous: list[str] = []
    any_drift = any_unver = False
    for n in base.nodes:
        if not n.source_hash:
            per_node[n.id] = "UNVERIFIABLE"
            any_unver = True
            continue
        if n.id in current_sources:
            cur = current_sources[n.id]
        elif n.source_ref in current_sources:
            if ref_counts.get(n.source_ref, 0) > 1:
                # shared ref: one slot cannot independently verify N nodes
                per_node[n.id] = "UNVERIFIABLE"
                ambiguous.append(n.id)
                any_unver = True
                continue
            cur = current_sources[n.source_ref]
        else:
            # no re-check material supplied -> cannot confirm freshness
            per_node[n.id] = "UNVERIFIABLE"
            any_unver = True
            continue
        cur_hash = cur[:16] if n.kind == "code" else _hash(cur)
        if cur_hash == n.source_hash:
            per_node[n.id] = "MATCH"
        else:
            per_node[n.id] = "DRIFT"
            any_drift = True
    # seal integrity: recompute the root over the CURRENT nodes
    recomputed = seal(base.nodes).root_hash
    seal_ok = (recomputed == base.seal.root_hash)
    if not seal_ok:
        any_drift = True
    overall = "DRIFT" if any_drift else ("UNVERIFIABLE" if any_unver else "MATCH")
    return {"overall": overall, "seal_intact": seal_ok, "per_node": per_node,
            "drifted": [k for k, v in per_node.items() if v == "DRIFT"],
            "unverifiable": [k for k, v in per_node.items() if v == "UNVERIFIABLE"],
            "ambiguous_ref": ambiguous}


def propose_write(base: KnowledgeBase, node: WikiNode,
                  current_sources: dict) -> tuple[bool, str]:
    """Witnessed write-back: admit a node into the base ONLY if its provenance is
    confirmed — it cites a source that is PRESENT and UNCHANGED. Refuses an
    ungrounded write (no source_hash), an absent source, or a drifted source (the
    node no longer matches what it cites). This is the guard the unattended-write
    second-brains lack: a hallucinated note with no valid grounding never lands.

    Scope (honest): this gates PROVENANCE (grounded, present, unchanged source),
    NOT the semantic faithfulness of a synthesized summary — that needs a real
    write-back oracle, never a learned judge in the accept path (C2). On accept,
    links and seal are recomputed so the base stays consistent."""
    if not node.source_hash:
        return (False, "REFUSED UNVERIFIABLE: no provenance (ungrounded write)")
    cur = current_sources.get(node.id, current_sources.get(node.source_ref))
    if cur is None:
        return (False, "REFUSED UNVERIFIABLE: cited source absent — cannot confirm grounding")
    cur_hash = cur[:16] if node.kind == "code" else _hash(cur)
    if cur_hash != node.source_hash:
        return (False, "REFUSED DRIFT: node does not match its cited source (hallucinated write)")
    base.nodes.append(node)
    base.links = derive_links(base.nodes)
    base.seal = seal(base.nodes)
    return (True, "ADMITTED SEALED: grounded write")


def to_markdown(n: WikiNode) -> str:
    """Export a node as Obsidian-compatible markdown WITH a provenance header
    Obsidian notes lack — so you get interop plus the faithfulness metadata."""
    front = [f"provenance: {n.provenance}", f"source: {n.source_ref}",
             f"source_hash: {n.source_hash or 'none'}", f"kind: {n.kind}"]
    if n.tier:
        front.append(f"scout_tier: {n.tier}")
    body = [f"# {n.title}", ""]
    if n.concepts:
        body.append("concepts: " + ", ".join(f"[[{c}]]" for c in n.concepts))
    return "---\n" + "\n".join(front) + "\n---\n" + "\n".join(body) + "\n"
