"""test_fold_index.py — recall verbatim facts from folded context, no embeddings.

Success criteria:
  - add + recall returns the span whose content matches the query, ranked.
  - a rarer query term surfaces the more specific span first.
  - the same span hash is never indexed twice; empty query -> [].
  - the index persists across instances.
  - index_compaction indexes exactly what a real compaction folded away, and the
    fact is recallable afterward.
"""
from harness.compaction import compact
from harness.fold_index import FoldIndex, index_compaction


def test_add_and_recall():
    idx = FoldIndex()
    idx.add("h1", [{"role": "user", "content": "the deploy key lives in the vault"}])
    idx.add("h2", [{"role": "user", "content": "we chose postgres for the database"}])
    hits = idx.recall("where is the deploy key")
    assert hits and hits[0]["span_hash"] == "h1"
    assert hits[0]["messages"][0]["content"] == "the deploy key lives in the vault"


def test_rarer_term_ranks_the_specific_span_first():
    idx = FoldIndex()
    idx.add("common", [{"role": "user", "content": "the the the config config"}])
    idx.add("specific", [{"role": "user", "content": "the kubernetes namespace is prod-eu"}])
    hits = idx.recall("kubernetes namespace")
    assert hits[0]["span_hash"] == "specific"


def test_content_addressed_no_duplicates_and_empty_query():
    idx = FoldIndex()
    idx.add("h1", [{"role": "user", "content": "alpha"}])
    idx.add("h1", [{"role": "user", "content": "DIFFERENT"}])   # same hash -> ignored
    assert idx.spans["h1"][0]["content"] == "alpha"
    assert idx.recall("") == []


def test_persists_across_instances(tmp_path):
    p = tmp_path / "fold_index.json"
    FoldIndex(p).add("h1", [{"role": "user", "content": "remember the release date is june"}])
    hits = FoldIndex(p).recall("release date")
    assert hits and hits[0]["span_hash"] == "h1"


def test_index_compaction_makes_folded_facts_recallable():
    # a long transcript with one buried fact; fold it, then recall the fact
    msgs = ([{"role": "user", "content": "TASK build the service " + "word " * 40}]
            + [{"role": "assistant", "content": f"step {i} " + "word " * 40} for i in range(1, 4)]
            + [{"role": "user", "content": "note: the admin endpoint is /internal/ctl-9x"}]
            + [{"role": "assistant", "content": f"step {i} " + "word " * 40} for i in range(4, 9)])
    idx = FoldIndex()
    result = compact(msgs, token_budget=200, keep_recent=3)
    assert result.compacted
    index_compaction(idx, msgs, result)
    hits = idx.recall("admin endpoint ctl")
    assert hits and any("ctl-9x" in m["content"] for m in hits[0]["messages"])


def test_agent_compaction_indexes_into_fold_index_for_recall():
    """Gap B falsifier: when a LocalAgent has a fold_index attached, compacting
    its history must index the folded span so recall_context can retrieve it.
    Before Phase 3 the agent discarded the folded span; this proves the wire."""
    from harness.local_agent import LocalAgent
    idx = FoldIndex()
    agent = LocalAgent(
        backends=[], compact_budget=200, compact_keep_recent=3, fold_index=idx)
    # a long history with one buried fact
    agent.history = (
        [{"role": "user", "content": "TASK build it " + "word " * 40}]
        + [{"role": "assistant", "content": f"step {i} " + "word " * 40} for i in range(1, 4)]
        + [{"role": "user", "content": "the secret token is tok-7q2-redacted"}]
        + [{"role": "assistant", "content": f"step {i} " + "word " * 40} for i in range(4, 9)])
    agent._maybe_compact()
    # the folded fact must now be recallable through the agent's own index
    recalled = agent.recall_context("secret token")
    assert recalled, "folded fact must be recallable after compaction"
    assert any("tok-7q2" in m["content"] for m in recalled)

    # without a fold_index, recall_context is a graceful no-op
    agent2 = LocalAgent(backends=[], compact_budget=200, compact_keep_recent=3)
    agent2.history = list(agent.history)
    assert agent2.recall_context("secret token") == []


def test_recall_carries_a_content_hash_derived_from_the_stored_span():
    import hashlib
    idx = FoldIndex()
    msgs = [{"role": "user", "content": "the launch code is alpha-seven"}]
    idx.add("caller-claimed-hash", msgs)
    hit = idx.recall("launch code", top_k=1)[0]
    assert "content_sha256" in hit
    # the content hash is derived from the stored content, not the caller key
    assert hit["content_sha256"] != "caller-claimed-hash"


def test_verify_catches_a_tampered_stored_span():
    idx = FoldIndex()
    idx.add("h1", [{"role": "user", "content": "original fact"}])
    assert idx.verify()["ok"] is True
    # tamper the stored content directly, leaving the key intact
    idx.spans["h1"] = [{"role": "user", "content": "forged fact"}]
    v = idx.verify()
    assert v["ok"] is False
    assert "h1" in v["tampered"]
