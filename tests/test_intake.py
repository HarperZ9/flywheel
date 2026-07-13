"""intake falsifier — a curated feed becomes flywheel build candidates, receipted.

Load-bearing properties:
  1. A thread naming a falsifiable mechanism outranks market-hype noise, and the
     hype does NOT become a build candidate.
  2. The digest is deterministic and content-addressed: same feed -> same hash
     and same verdict counts (a re-checkable receipt, not a vibe).
  3. The curator gate rejects malformed feed rows loudly (no silent signal loss).
  4. Actionable threads flow through to evolve as gated build candidates.
"""
import json

import pytest

from harness import intake

FEED = [
    {"id": "mech", "ref": "x:1",
     "text": "verification gates bound throughput, not agent count; the oracle "
             "is the real limit and a benchmark ablation would measure it."},
    {"id": "local", "ref": "x:2",
     "text": "run capable models locally and offline on commodity hardware with "
             "open-source weights, no cloud."},
    {"id": "hype", "ref": "x:3",
     "text": "GPT drops this week, hyped as a leap, fewer guardrails, pricing "
             "pressure on everyone."},
]


def test_actionable_outranks_and_hype_is_not_a_candidate():
    d = intake.digest(FEED, feed_id="test")
    assert d.verdict_counts["ACTIONABLE"] >= 1
    assert d.verdict_counts["NOISE"] >= 1
    titles = " ".join(t["title"] for t in d.actionable).lower()
    assert "gpt drops" not in titles  # hype never a build candidate
    gated = d.build_candidates["gated"] + d.build_candidates["auto_apply"]
    assert gated, "an actionable mechanism must surface as a build candidate"


def test_digest_is_deterministic_and_hashed():
    d1 = intake.digest(FEED, feed_id="test")
    d2 = intake.digest(FEED, feed_id="test")
    assert d1.feed_hash == d2.feed_hash
    assert d1.verdict_counts == d2.verdict_counts
    # hash binds content: change one source, hash moves
    mutated = [dict(FEED[0], text=FEED[0]["text"] + " edited")] + FEED[1:]
    assert intake.digest(mutated, feed_id="test").feed_hash != d1.feed_hash


def test_curator_gate_rejects_malformed_rows():
    with pytest.raises(ValueError):
        intake.digest([{"id": "no-text-field"}], feed_id="bad")
    with pytest.raises(ValueError):
        intake.digest([{"id": "dup", "text": "a"}, {"id": "dup", "text": "b"}],
                      feed_id="bad")


def test_load_feed_accepts_object_and_list(tmp_path):
    obj = tmp_path / "feed.json"
    obj.write_text(json.dumps({"source": "s", "catalog": FEED}), encoding="utf-8")
    fid, cat = intake.load_feed(obj)
    assert fid == "s" and len(cat) == 3
    bare = tmp_path / "bare.json"
    bare.write_text(json.dumps(FEED), encoding="utf-8")
    _, cat2 = intake.load_feed(bare)
    assert len(cat2) == 3


def test_efficiency_feed_composes_into_same_cycle():
    eff = {"improvement_candidates": ["reduce oracle calls via escalation prune"]}
    d = intake.digest(FEED, feed_id="test", efficiency_feed=eff)
    descs = " ".join(c["description"] for c in
                     d.build_candidates["auto_apply"] + d.build_candidates["gated"]).lower()
    assert "escalation" in descs  # telemetry candidate ranked alongside research
