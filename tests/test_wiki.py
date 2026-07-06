"""wiki falsifier — the verified second brain must catch what Obsidian cannot.

Load-bearing properties (each the thing a pile of manual markdown lacks):
  1. A node whose SOURCE CHANGED is caught as DRIFT (freshness/faithfulness).
  2. A node with no provenance is UNVERIFIABLE, never silently MATCH.
  3. The base is content-sealed: tamper any node -> root hash shifts -> DRIFT.
  4. Links are DERIVED from shared concepts, deterministic (not hand-typed).
  5. Code (index_wiki) + corpus (intake) compose into one sealed base.
  6. Exported markdown carries a provenance header Obsidian notes don't have.
"""
import pytest

from harness import wiki

CATALOG = [
    {"id": "a", "ref": "src:a",
     "text": "oracle verification cache diversity escalation search"},
    {"id": "b", "ref": "src:b",
     "text": "oracle verification throughput benchmark ablation"},
    {"id": "c", "ref": "src:c",
     "text": "the history of the violin bow in baroque music"},
]


def _sources(catalog):
    # verify() re-hashes the corpus source string, which from_corpus builds as
    # title+text+summary; these rows carry only text, so the source == text.
    return {r["ref"]: r["text"] for r in catalog}


def test_unchanged_source_is_match():
    base = wiki.build(CATALOG)
    v = wiki.verify(base, _sources(CATALOG))
    assert v["overall"] == "MATCH"
    assert v["seal_intact"] is True


def test_changed_source_is_drift():
    # THE property Obsidian cannot answer: which notes went stale?
    base = wiki.build(CATALOG)
    srcs = _sources(CATALOG)
    srcs["src:a"] = srcs["src:a"] + " (edited upstream)"
    v = wiki.verify(base, srcs)
    assert v["overall"] == "DRIFT"
    assert "corpus/a" in v["drifted"]
    assert "corpus/b" not in v["drifted"]


def test_missing_provenance_is_unverifiable_never_match():
    base = wiki.build([{"id": "x", "ref": "src:x", "text": ""}])  # empty -> no hash
    node = base.nodes[0]
    assert node.provenance == "UNVERIFIABLE"
    v = wiki.verify(base, {})
    assert v["overall"] == "UNVERIFIABLE"
    assert "corpus/x" in v["unverifiable"]


def test_source_not_resupplied_cannot_claim_fresh():
    base = wiki.build(CATALOG)
    v = wiki.verify(base, {})  # no current material -> cannot confirm freshness
    assert v["overall"] == "UNVERIFIABLE"
    assert set(v["unverifiable"]) == {"corpus/a", "corpus/b", "corpus/c"}


def test_tampered_node_breaks_seal():
    base = wiki.build(CATALOG)
    base.nodes[0].source_hash = "deadbeefdeadbeef"  # mutate after sealing
    v = wiki.verify(base, _sources(CATALOG))
    assert v["seal_intact"] is False
    assert v["overall"] == "DRIFT"


def test_links_are_derived_and_deterministic():
    l1 = wiki.build(CATALOG).links
    l2 = wiki.build(CATALOG).links
    assert l1 == l2
    ab = [(a, b) for a, b, _ in l1 if {a, b} == {"corpus/a", "corpus/b"}]
    assert ab, "a and b share >=2 concepts (oracle, verification) -> a link"
    # c shares no harness concepts -> no link to it
    assert not any("corpus/c" in (a, b) for a, b, _ in l1)


def test_code_and_corpus_compose():
    manifest = {"commit": "x", "pages": [
        {"id": "module/harness/oracle", "sha256": "a" * 64},
        {"id": "overview", "sha256": "b" * 64}]}
    base = wiki.build(CATALOG, index_manifest=manifest)
    kinds = {n.kind for n in base.nodes}
    assert kinds == {"corpus", "code"}
    code = [n for n in base.nodes if n.kind == "code"]
    assert code and all(n.provenance == "SEALED" for n in code)


def test_code_node_drifts_when_page_hash_changes():
    manifest = {"commit": "x", "pages": [{"id": "module/harness/chain", "sha256": "c" * 64}]}
    base = wiki.build([], index_manifest=manifest)
    node = base.nodes[0]
    fresh = {node.source_ref: "c" * 64}      # same page hash -> MATCH
    assert wiki.verify(base, fresh)["overall"] == "MATCH"
    changed = {node.source_ref: "d" * 64}    # code changed -> DRIFT
    assert wiki.verify(base, changed)["overall"] == "DRIFT"


def test_markdown_export_carries_provenance():
    node = wiki.build(CATALOG).nodes[0]
    md = wiki.to_markdown(node)
    assert "provenance:" in md and "source_hash:" in md and "source:" in md


def test_empty_base_is_safe():
    base = wiki.build([])
    assert base.nodes == [] and base.links == []
    assert base.seal.root_hash == "empty"
    assert wiki.verify(base, {})["overall"] == "MATCH"
