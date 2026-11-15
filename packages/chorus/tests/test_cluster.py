from chorus.item import DiscourseItem
from chorus.sentiment import Scored
from chorus.synthesize import item_weight, cluster


def _s(text, eng=0, compound=0.0, i="x"):
    it = DiscourseItem(i, "video", "v", None, "a", text, eng, None, {})
    return Scored(it, compound, "lexicon", ())


def test_weight_monotonic_in_engagement_and_sentiment():
    assert item_weight(100, 0.0) > item_weight(10, 0.0)
    assert item_weight(10, 0.9) > item_weight(10, 0.0)
    assert item_weight(0, 0.0) == 0.0


def test_cluster_groups_similar_and_separates_distinct():
    items = [
        _s("the sound design and audio mix was incredible", i="a"),
        _s("loved the sound design, great audio mixing", i="b"),
        _s("the plot and story writing made no sense", i="c"),
        _s("terrible story, the plot writing was weak", i="d"),
    ]
    groups = cluster(items, threshold=0.12)
    ids = sorted(sorted(s.item.id for s in g) for g in groups)
    assert ["a", "b"] in ids and ["c", "d"] in ids
    assert sum(len(g) for g in groups) == 4     # partition: every item exactly once


def test_cluster_is_deterministic():
    items = [_s("alpha beta gamma", i=str(n)) for n in range(5)]
    assert [[s.item.id for s in g] for g in cluster(items)] == \
           [[s.item.id for s in g] for g in cluster(items)]
