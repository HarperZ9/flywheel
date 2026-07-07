"""verified second brain falsifier — beats the unverified competitors where it counts.

The differentiators the Obsidian second-brains lack: (1) a real FRESHNESS verdict
(which notes drifted), and (2) witnessed write-back (a hallucinated note is
refused). Built by composing feeds + intake + wiki — no new primitives.
"""
from harness import wiki
from harness.second_brain import build_brain, refresh, write_note, brain_report, VerifiedBrain
from harness.wiki import WikiNode

SESSIONS = [{"id": "s1", "title": "harness build", "text": "oracle verification cache diversity"}]
SCRAPE = {"subreddits": {}, "threads": [
    {"id": "t1", "title": "verified inference", "text": "verification gates bound throughput", "sub": "ml", "theme": "harness"}]}


def _brain():
    from harness import feeds
    sess = feeds.normalize_sessions(SESSIONS)
    scr = feeds.normalize_scrape(SCRAPE)
    return build_brain(sess, scr, feed_id="test-brain")


def test_build_brain_composes_pillars_into_a_sealed_wiki():
    b = _brain()
    assert isinstance(b, VerifiedBrain)
    assert b.n_sources == 2 and len(b.wiki.nodes) == 2
    assert b.wiki.seal.root_hash                      # sealed
    assert "sealed nodes" in brain_report(b)


def test_refresh_gives_a_real_freshness_verdict():
    b = _brain()
    # supply current material for both nodes, one DRIFTED
    cur = {}
    for n in b.wiki.nodes:
        # id-keyed; drift the first node's source
        cur[n.id] = "TOTALLY DIFFERENT CONTENT" if n.id == b.wiki.nodes[0].id else \
            _orig_text(b, n.id)
    r = refresh(b, cur)
    assert b.wiki.nodes[0].id in r["drifted"], "a changed source must report DRIFT"
    assert r["overall"] == "DRIFT"


def test_write_note_refuses_hallucinated_admits_grounded():
    b = _brain()
    n0 = len(b.wiki.nodes)
    # hallucinated: no provenance
    bad = WikiNode(id="corpus/hallucinated", kind="corpus", title="x",
                   source_ref="src:x", source_hash="")
    ok, reason = write_note(b, bad, {"src:x": "anything"})
    assert not ok and len(b.wiki.nodes) == n0        # refused, brain unchanged

    # grounded: source present + hash matches
    src = "a genuinely new grounded note about oracles"
    good = WikiNode(id="corpus/new", kind="corpus", title="new", source_ref="src:new",
                    source_hash=wiki._hash(src), concepts=["oracle"], tier="INSPIRATION")
    ok2, reason2 = write_note(b, good, {"src:new": src})
    assert ok2 and len(b.wiki.nodes) == n0 + 1       # admitted + re-sealed


def _orig_text(brain, node_id):
    # recover the ingested text for a node from the catalog (by matching node id tail)
    for row in brain.catalog:
        if node_id.endswith(row["id"]):
            return row["text"]
    return ""
