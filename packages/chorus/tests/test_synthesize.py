from chorus.item import DiscourseItem
from chorus.sentiment import Scored
from chorus.synthesize import synthesize, Digest, Theme


def _s(text, eng, compound, i):
    it = DiscourseItem(i, "video", "vid", None, "a", text, eng, None, {})
    return Scored(it, compound, "lexicon", ())


def test_synthesize_builds_ranked_themes_with_distribution_and_dissent():
    scored = [
        _s("the audio mix sound design was great", 50, 0.6, "a"),
        _s("loved the sound design and audio", 10, 0.5, "b"),
        _s("actually the audio mixing was bad and muddy", 30, -0.5, "c"),
        _s("the plot story writing made no sense", 5, -0.4, "d"),
    ]
    d = synthesize(scored, threshold=0.12)
    assert isinstance(d, Digest) and d.responds_to == "vid" and d.n_items == 4
    assert d.themes == tuple(sorted(d.themes, key=lambda t: -t.weighted_score))
    audio = max(d.themes, key=lambda t: t.size)
    assert audio.size == 3
    assert 0.0 <= audio.sentiment["pos"] <= 1.0
    # a minority negative voice exists in a majority-positive theme -> dissent surfaced
    assert audio.dissent == "c"
    # representative is the highest-weight item (engagement 50)
    assert audio.representative == "a"


def test_controversy_is_high_for_a_split_theme_and_zero_for_consensus():
    # a theme where voices are fiercely split pos/neg is contested; one where they
    # all agree is consensus. controversy quantifies that, in [0, 1].
    split = synthesize([_s("the sound design mix", 5, 0.9, "a"),
                        _s("the sound design mix", 5, -0.9, "b")], threshold=0.0)
    consensus = synthesize([_s("the sound design mix", 5, 0.8, "c"),
                            _s("the sound design mix", 5, 0.8, "d")], threshold=0.0)
    assert 0.0 <= split.themes[0].controversy <= 1.0
    assert split.themes[0].controversy > 0.8          # ±0.9 split -> near the ceiling
    assert consensus.themes[0].controversy == 0.0     # identical sentiment -> no contest
    assert split.themes[0].controversy > consensus.themes[0].controversy


def test_contested_aspects_surface_two_sided_topics_immune_to_lexical_split():
    # lexical clustering separates "battery is amazing" from "battery is terrible" into
    # different themes; aspect contestedness gathers EVERY item mentioning "battery" and
    # sees the split. one-sided praise ("screen") is not contested.
    scored = [
        _s("the battery life is incredible amazing", 50, 0.7, "a"),
        _s("battery life is amazing best ever", 40, 0.6, "b"),
        _s("the battery is terrible drains fast", 45, -0.6, "c"),
        _s("awful battery life so disappointing", 30, -0.5, "d"),
        _s("the screen display is gorgeous bright", 40, 0.6, "e"),
        _s("stunning screen display love it", 35, 0.6, "f"),
        _s("beautiful screen display colors", 20, 0.5, "g"),
    ]
    d = synthesize(scored, threshold=0.2)
    terms = [c["term"] for c in d.contested]
    assert "battery" in terms                          # genuinely two-sided -> contested
    assert "screen" not in terms and "display" not in terms   # one-sided praise -> excluded
    top = d.contested[0]
    assert top["mentions"] >= 3 and top["pos"] >= 0 and top["neg"] > 0
    assert 0.0 <= top["contested"] <= 1.0


def test_contested_is_empty_when_nothing_is_two_sided():
    scored = [_s("the screen is gorgeous bright", 5, 0.6, "a"),
              _s("the screen is gorgeous vivid", 5, 0.6, "b"),
              _s("the screen is gorgeous sharp", 5, 0.6, "c")]
    assert synthesize(scored, threshold=0.0).contested == ()


def test_theme_with_no_minority_has_no_dissent():
    scored = [_s("great", 5, 0.6, "a"), _s("great wonderful", 5, 0.6, "b")]
    d = synthesize(scored, threshold=0.0)
    assert d.themes[0].dissent is None


def test_digest_surfaces_engagement_coverage_and_coarseness():
    it_present = DiscourseItem("a", "video", "v", None, "x", "great sound", 12, None,
                               {"engagement_present": True})
    it_absent = DiscourseItem("b", "video", "v", None, "y", "bad sound", 0, None,
                              {"engagement_present": False})
    d = synthesize([Scored(it_present, 0.5, "lexicon", ()), Scored(it_absent, -0.5, "lexicon", ())])
    assert d.method["engagement_coverage"] == {"present": 1, "total": 2}
    assert "English-only" in d.method["coarseness"] and "never a verdict" in d.method["coarseness"]


def test_mixed_target_corpus_is_labelled_mixed_not_the_first_row():
    a = Scored(DiscourseItem("a", "video", "vid1", None, "x", "hi there", 0, None, {}), 0.0, "lexicon", ())
    b = Scored(DiscourseItem("b", "reddit", "post9", None, "y", "hi there", 0, None, {}), 0.0, "lexicon", ())
    d = synthesize([a, b])
    assert d.responds_to == "(mixed)" and d.method["distinct_targets"] == 2


def test_non_latin_text_forms_terms_and_does_not_crash():
    scored = [_s("这个视频很好 sound design", 3, 0.2, "a"), _s("这个视频很好 sound design", 2, 0.2, "b")]
    d = synthesize(scored, threshold=0.1)
    assert d.n_items == 2 and len(d.themes) == 1     # shared non-Latin + Latin terms cluster them


def test_theme_label_filters_generic_modal_words():
    # Break caught: raw frequency labels "can / have / some" instead of the topic the
    # cluster actually shares.
    scored = [
        _s("can have some battery diagnostics", 2, 0.0, "a"),
        _s("can have some battery diagnostics", 2, 0.0, "b"),
        _s("can have some battery diagnostics", 2, 0.0, "c"),
    ]
    d = synthesize(scored, threshold=0.0)
    terms = d.themes[0].label.split(" / ")
    assert terms == ["battery", "diagnostics"]
    assert d.themes[0].label_quality["support"] == "cluster"
    assert d.themes[0].label_quality["warnings"] == ()


def test_theme_label_survives_negation_and_generic_words():
    # Break caught: negation-heavy operational requests get labelled by generic
    # function words instead of the shared product topic.
    scored = [
        _s("can have because never rollback checkpoint plan", 2, -0.2, "a"),
        _s("can have because without rollback checkpoint preview", 2, -0.2, "b"),
        _s("can have because not rollback checkpoint consent", 2, -0.2, "c"),
    ]
    d = synthesize(scored, threshold=0.0)
    terms = d.themes[0].label.split(" / ")
    assert terms == ["checkpoint", "rollback"]
    assert all(term not in {"can", "have", "because", "never", "without"} for term in terms)


def test_singleton_theme_carries_weak_support_warning():
    # Break caught: a single comment can be useful evidence, but it must not be
    # rendered as a coherent crowd theme without an explicit support warning.
    d = synthesize([_s("quota tracker limits", 0, 0.0, "a")])
    assert d.themes[0].label == "limits / quota / tracker"
    assert d.themes[0].label_quality["support"] == "singleton"
    assert d.themes[0].label_quality["warnings"] == ("singleton_theme",)


def test_mixed_cluster_with_low_term_coverage_warns_weak_label_support():
    # Break caught: a heterogeneous cluster with only two voices per candidate
    # term must not present a specific label as if it summarized the cluster.
    scored = [
        _s("payment receipt audit", 2, 0.0, "a"),
        _s("payment receipt export", 2, 0.0, "b"),
        _s("rollback checkpoint preview", 2, 0.0, "c"),
        _s("rollback checkpoint consent", 2, 0.0, "d"),
        _s("quota tracker budget", 2, 0.0, "e"),
        _s("quota tracker limits", 2, 0.0, "f"),
    ]
    d = synthesize(scored, threshold=0.0)
    assert d.themes[0].label_quality["support"] == "weak"
    assert d.themes[0].label_quality["warnings"] == ("weak_label_support",)
