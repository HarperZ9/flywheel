"""scout falsifier — the sly fox isolates falsifiable-actionable threads.

The load-bearing property: a thread implying a MEASURABLE MECHANISM (method,
metric, ablation) ranks ACTIONABLE above a relevant-but-metaphorical thread
(INSPIRATION) above irrelevant noise (NOISE). The feed artifact surfaces only
the actionable ones as build candidates. This is the crucible's "state the
falsification condition" discipline applied at curation scale.
"""
import pytest

from harness.scout import (assess, rank, actionable_only, synthesize_feed,
                           HARNESS_VOCAB, FALSIFIABILITY_SIGNALS)

CATALOG = [
    {
        "id": "falsifiable-1",
        "title": "A method for verifier-guided search that improves pass rate via dense oracle reward",
        "ref": "http://arxiv.org/abs/xxx1",
    },
    {
        "id": "falsifiable-2",
        "title": "Token-budget ablation: reducing oracle calls increases throughput on best-of-N",
        "ref": "http://arxiv.org/abs/xxx2",
    },
    {
        "id": "inspiration-1",
        # relevant (names model/context/memory) but no falsifiable mechanism
        # -> INSPIRATION. (Was "emergent ... entropy", which only reached the
        # 2-hit floor via a phantom substring match of "merge" in "emergent";
        # word-boundary matching removed that, so the example now carries real
        # concepts.)
        "title": "Emergent intelligence from scaling model context length and long-term memory",
        "ref": "http://arxiv.org/abs/xxx3",
    },
    {
        "id": "noise-1",
        "title": "A study of crop rotation patterns in medieval agriculture",
        "ref": "http://arxiv.org/abs/xxx4",
    },
    {
        "id": "noise-2",
        "title": "The history of the violin bow in baroque music",
        "ref": "http://arxiv.org/abs/xxx5",
    },
]


def test_actionable_ranked_above_inspiration_above_noise():
    ranked = rank(CATALOG)
    verdicts = [a.verdict for a in ranked]
    assert verdicts.index("ACTIONABLE") < verdicts.index("INSPIRATION")
    assert "NOISE" in verdicts


def test_falsifiable_thread_is_actionable():
    a = assess(CATALOG[0])
    assert a.falsifiable
    assert a.verdict == "ACTIONABLE"
    assert a.suggested_extension  # non-empty: points at a build candidate


def test_metaphorical_thread_is_inspiration_not_actionable():
    a = assess(CATALOG[2])
    assert a.verdict == "INSPIRATION"
    assert not a.falsifiable or a.verdict != "ACTIONABLE"


def test_irrelevant_is_noise():
    assert assess(CATALOG[3]).verdict == "NOISE"
    assert assess(CATALOG[4]).verdict == "NOISE"


def test_actionable_only_filters():
    actionable = actionable_only(CATALOG)
    assert all(a.verdict == "ACTIONABLE" for a in actionable)
    assert len(actionable) >= 1
    assert all(a.source_id not in ("noise-1", "noise-2") for a in actionable)


def test_synthesize_feed_isolates_actionable_for_pipeline():
    feed = synthesize_feed(rank(CATALOG))
    assert "actionable" in feed["feed_summary"].lower()
    assert all("measurable mechanism" in t["suggested_extension"]
               for t in feed["actionable_threads"])
    assert feed["noise_count"] == 2
    assert len(feed["actionable_threads"]) >= 1


def test_relevance_scales_with_vocab_overlap():
    high = assess({"id": "x", "title": "oracle verification cache diversity escalation search entropy"})
    low = assess({"id": "y", "title": "oracle"})
    assert high.verdict != "NOISE", "6 vocab hits must be relevant"
    assert low.verdict == "NOISE", "single hit below min-signal gate must be NOISE"


def test_empty_catalog_is_safe():
    assert rank([]) == []
    assert synthesize_feed([])["noise_count"] == 0
