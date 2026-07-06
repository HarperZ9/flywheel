"""witnessed write-back falsifier — a hallucinated wiki write never lands.

The competitor parity + surpass: the leopardracer second-brain writes to Obsidian
unattended with zero verification. propose_write refuses any write whose
provenance cannot be confirmed (no source, absent source, or a source that no
longer matches), while admitting a grounded write and re-sealing the base.
"""
from harness import wiki
from harness.wiki import WikiNode, propose_write, verify, MIN_SHARED_CONCEPTS  # noqa: F401

CATALOG = [
    {"id": "a", "ref": "src:a", "text": "oracle verification cache diversity"},
]


def _base():
    return wiki.build(CATALOG)


def test_grounded_write_is_admitted_and_resealed():
    base = _base()
    n0 = len(base.nodes)
    root0 = base.seal.root_hash
    src = "oracle verification throughput benchmark"
    node = WikiNode(id="corpus/new", kind="corpus", title="new note",
                    source_ref="src:new", source_hash=wiki._hash(src),
                    concepts=["oracle", "verification"], tier="INSPIRATION")
    ok, reason = propose_write(base, node, {"src:new": src})
    assert ok and "ADMITTED" in reason
    assert len(base.nodes) == n0 + 1
    assert base.seal.root_hash != root0, "the base must re-seal after a write"
    assert verify(base, {"src:new": src, "src:a": "oracle verification cache diversity"})["overall"] != "DRIFT"


def test_ungrounded_write_is_refused():
    base = _base()
    n0 = len(base.nodes)
    node = WikiNode(id="corpus/hallucinated", kind="corpus", title="no source",
                    source_ref="src:x", source_hash="")     # no provenance
    ok, reason = propose_write(base, node, {"src:x": "anything"})
    assert not ok and "UNVERIFIABLE" in reason
    assert len(base.nodes) == n0, "an ungrounded write must not land"


def test_absent_source_is_refused():
    base = _base()
    node = WikiNode(id="corpus/n", kind="corpus", title="t", source_ref="src:n",
                    source_hash=wiki._hash("some source"))
    ok, reason = propose_write(base, node, {})               # source not supplied
    assert not ok and "absent" in reason


def test_drifted_source_is_refused_as_hallucination():
    base = _base()
    # the node claims source_hash of TEXT-1 but the actual current source is TEXT-2
    node = WikiNode(id="corpus/n", kind="corpus", title="t", source_ref="src:n",
                    source_hash=wiki._hash("what the note claims the source says"))
    ok, reason = propose_write(base, node, {"src:n": "what the source ACTUALLY says"})
    assert not ok and "DRIFT" in reason
    assert node.id not in {x.id for x in base.nodes}
