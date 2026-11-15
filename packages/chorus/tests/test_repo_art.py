"""The drawings in the README, held against the code they describe.

The art gate settles whether a drawing fits its columns and matches the spec it
was rendered from. Both sides of that check read the same JSON, so it cannot
settle whether a drawing is TRUE. That is what this file is for: every count,
threshold and rule the three drawings put on the page is asserted here against
the code that produces it, so a claim that stops holding fails the suite rather
than staying on the page. The pipeline already has its own tests beside it, and
nothing here repeats them.
"""
import json
import math
import sys
from pathlib import Path

from chorus.item import DiscourseItem, normalize
from chorus.receipt import DigestReceipt, digest_body_sha
from chorus.sentiment import (_INTENSIFIERS, _LEXICON, _NEGATORS, score,
                              score_text)
from chorus.synthesize import cluster, contested_aspects, item_weight, synthesize

ROOT = Path(__file__).resolve().parents[1]
DRAWINGS = ("chorus-header.svg", "synthesis-lane.svg", "verify-lane.svg",
            "method-table.svg")


def _spec() -> dict:
    return json.loads((ROOT / "docs/art/chorus.art.json").read_text(encoding="utf-8"))


def _readme() -> str:
    return (ROOT / "README.md").read_text(encoding="utf-8")


def _items(rows):
    return [DiscourseItem(i, "video", "v", None, "au", t, e, None, {})
            for i, t, e in rows]


def test_every_drawing_is_committed_and_reaches_the_page():
    """A rendered file nobody embeds is a file nobody sees, so both are checked."""
    page = _readme()
    front = page
    # The previous header left the README on 4 October 2026 and is recorded in the brand notes;
    # a page here is the README or a doc under docs/, the same set tools/check_repo_art.py uses.
    page += "".join(q.read_text(encoding="utf-8") for q in sorted((ROOT / "docs").rglob("*.md")))
    for name in DRAWINGS:
        assert (ROOT / "docs/art" / name).exists(), name
        assert f"docs/art/{name}" in page, name
    for hero in ("docs/art/hero-dark.svg", "docs/art/hero-light.svg"):
        assert (ROOT / hero).is_file() and hero in front, hero


def test_the_alt_text_on_the_page_is_the_alt_text_in_the_spec():
    """A screen reader gets the alt text, not the picture, so the two are pinned."""
    spec = _spec()
    page = _readme()
    checked = 0
    for drawing in spec["flows"] + spec["cards"]:
        assert f'![{drawing["alt"]}](docs/art/{drawing["file"]})' in page
        checked += 1
    assert checked == 3


def test_the_lexicon_is_thirty_words_split_evenly_inside_its_range():
    """The card reads thirty words, fifteen each way, valence in minus three to three."""
    assert len(_LEXICON) == 30
    assert sum(1 for v in _LEXICON.values() if v > 0) == 15
    assert sum(1 for v in _LEXICON.values() if v < 0) == 15
    assert all(-3.0 <= v <= 3.0 for v in _LEXICON.values())


def test_ten_intensifiers_and_nine_negators():
    """Both counts are drawn on the card, and both tables are open to edit."""
    assert len(_INTENSIFIERS) == 10
    assert len(_NEGATORS) == 9


def test_an_intensifier_widens_and_a_dampener_narrows():
    """The card says extremely widens a valence and slightly pulls it in."""
    plain, _ = score_text("good")
    wider, _ = score_text("extremely good")
    narrower, _ = score_text("slightly good")
    assert wider > plain > narrower > 0


def test_a_negation_flips_the_sign_and_keeps_most_of_the_size():
    """The card says a negation flips sign and keeps about three quarters."""
    plain, _ = score_text("good")
    negated, _ = score_text("not good")
    assert negated < 0 < plain
    assert 0.6 < abs(negated) / plain < 0.9


def test_all_caps_counts_more_and_marks_stop_counting_after_four():
    """Two emphases on the card: an all-caps word, and up to four marks."""
    plain, _ = score_text("good")
    shouted, _ = score_text("GOOD")
    assert shouted > plain
    four, _ = score_text("good!!!!")
    six, _ = score_text("good!!!!!!")
    assert four > plain
    assert six == four


def test_the_compound_never_leaves_minus_one_to_one():
    """The drawn range, checked at the top of the lexicon rather than assumed."""
    loud = " ".join(["wonderful excellent amazing"] * 40)
    grim = " ".join(["awful terrible worst"] * 40)
    high, _ = score_text(loud)
    low, _ = score_text(grim)
    assert 0 < high < 1.0
    assert -1.0 < low < 0
    assert score_text("")[0] == 0.0


def test_the_squash_divides_by_the_root_of_itself_squared_plus_fifteen():
    """The card names the formula, so the formula is checked, not paraphrased."""
    total = _LEXICON["good"]
    expected = round(total / math.sqrt(total * total + 15.0), 4)
    assert score_text("good")[0] == expected


def test_the_weight_is_log_engagement_times_sentiment_intensity():
    """The drawn formula: log1p(engagement) * (1 + k * abs(compound)), k of a half."""
    assert item_weight(0, 0.9) == 0.0
    assert item_weight(10, 0.0) == math.log1p(10)
    assert item_weight(10, 1.0) == math.log1p(10) * 1.5
    assert item_weight(-5, 0.5) == 0.0


def test_a_loud_comment_nobody_engaged_with_stays_small():
    """The claim the weight row makes, checked as an ordering rather than a formula."""
    assert item_weight(1, 1.0) < item_weight(100, 0.0)


def test_the_cluster_defaults_are_512_dimensions_at_eighteen_hundredths():
    """Both numbers are drawn on the card, and both are keyword defaults."""
    import inspect
    params = inspect.signature(cluster).parameters
    assert params["dims"].default == 512
    assert params["threshold"].default == 0.18


def test_clustering_seeds_the_most_engaged_first_and_re_derives():
    """The lane says seeded most-engaged first, so it re-derives identically."""
    rows = [("a", "sound design is great", 2), ("b", "sound design is great", 90),
            ("c", "the plot was bad", 5)]
    first = cluster(score(_items(rows)), threshold=0.1)
    second = cluster(score(_items(rows)), threshold=0.1)
    assert [[s.item.id for s in g] for g in first] == [[s.item.id for s in g] for g in second]
    assert len(first) == 2


def test_controversy_is_zero_at_consensus_and_rises_with_a_split():
    """The card reads zero at consensus at any volume, near one at a hard split."""
    agreed = synthesize(score(_items([
        ("a", "the sound is wonderful", 3), ("b", "the sound is wonderful", 3)])),
        threshold=0.1)
    split = synthesize(score(_items([
        ("a", "the sound is wonderful", 3), ("b", "the sound is awful", 3)])),
        threshold=0.1)
    assert agreed.themes[0].controversy == 0.0
    assert split.themes[0].controversy > 0.3
    assert all(0.0 <= t.controversy <= 1.0 for t in split.themes)


def test_a_contested_term_needs_three_voices_and_both_sides():
    """One-sided praise is not a fight, and the card says so in the aspect row."""
    praise = _items([("a", "the battery is wonderful", 1),
                     ("b", "the battery is excellent", 1),
                     ("c", "the battery is amazing", 1)])
    terms = [row["term"] for row in
             contested_aspects(score(praise), pos_cut=0.1, neg_cut=-0.1)]
    assert "battery" not in terms

    split = _items([("a", "the battery is wonderful", 1),
                    ("b", "the battery is awful", 1),
                    ("c", "the battery is terrible", 1)])
    rows = contested_aspects(score(split), pos_cut=0.1, neg_cut=-0.1)
    battery = [row for row in rows if row["term"] == "battery"]
    assert battery and battery[0]["mentions"] == 3

    thin = _items([("a", "the battery is wonderful", 1),
                   ("b", "the battery is awful", 1)])
    assert not [r for r in contested_aspects(score(thin), pos_cut=0.1, neg_cut=-0.1)
                if r["term"] == "battery"]


def test_a_split_topic_survives_the_clustering_that_would_hide_it():
    """The return edge on the synthesis lane, checked rather than asserted.

    Praise and complaint about one topic use different words, so lexical
    clustering files them apart. The aspect lens reads every mentioning voice,
    which is why the fight still gets reported.
    """
    rows = [("a", "battery charge holds wonderful, great endurance", 5),
            ("b", "battery charge holds excellent, great endurance", 5),
            ("c", "battery drains quickly, awful terrible waste", 5),
            ("d", "battery drains quickly, worst hate waste", 5)]
    digest = synthesize(score(_items(rows)))
    grouped = [set(theme.item_ids) for theme in digest.themes]
    assert {"a", "b"} in grouped and {"c", "d"} in grouped
    assert all(theme.controversy < 0.05 for theme in digest.themes)
    signs = sorted(theme.sentiment["mean_compound"] for theme in digest.themes)
    assert signs[0] < -0.5 and signs[-1] > 0.5
    assert "battery" in [row["term"] for row in digest.contested]


def test_the_digest_surfaces_at_most_twelve_contested_aspects():
    """The drawn cap, checked against a corpus wide enough to exceed it."""
    rows = []
    words = ["battery", "screen", "sound", "camera", "price", "weight", "speed",
             "shape", "colour", "cable", "charger", "casing", "buttons", "logo"]
    for index, word in enumerate(words):
        rows.append((f"p{index}", f"the {word} is wonderful and great", 3))
        rows.append((f"q{index}", f"the {word} is awful and terrible", 3))
        rows.append((f"r{index}", f"the {word} is amazing, love it", 3))
    digest = synthesize(score(_items(rows)))
    assert len(digest.contested) == 12


def test_the_receipt_carries_seven_fields():
    """The card lists them by name, so the dataclass is held to the same seven."""
    assert list(DigestReceipt.__dataclass_fields__) == [
        "input_sha256", "lexicon_vocab_sha", "cluster_params", "weight_formula",
        "model_ref", "digest_sha256", "method_version"]


def test_the_model_overlay_stays_out_of_the_digest_hash():
    """The accented row, and the third outcome on the synthesis lane."""
    import dataclasses
    scored = score(_items([("a", "the sound is fine", 4), ("b", "the plot was bad", 2)]))
    digest = synthesize(scored)
    opinionated = dataclasses.replace(digest, model_layer=(
        {"item_id": "a", "model_compound": 0.9, "provenance": "model:some-model"},))
    assert digest_body_sha(opinionated) == digest_body_sha(digest)


def test_an_absent_engagement_signal_is_recorded_absent():
    """The last row of the card, and the second stage of the synthesis lane."""
    rows = [{"id": "a", "kind": "comment", "ref": "v", "text": "hello", "meta": {}},
            {"id": "b", "kind": "comment", "ref": "v", "text": "hi",
             "meta": {"like_count": 0}},
            {"id": "c", "kind": "video", "ref": "v", "text": "not discourse"}]
    items = normalize(rows)
    assert [item.id for item in items] == ["a", "b"]
    assert items[0].engagement == 0 and items[0].meta["engagement_present"] is False
    assert items[1].engagement == 0 and items[1].meta["engagement_present"] is True
    coverage = synthesize(score(items)).method["engagement_coverage"]
    assert coverage == {"present": 1, "total": 2}


def test_a_changed_lexicon_fails_the_receipt():
    """The return edge on the verify lane, checked by moving one word."""
    from chorus import sentiment
    from chorus.receipt import verify
    scored = score(_items([("a", "the sound is great", 4), ("b", "the plot was bad", 2)]))
    digest = synthesize(scored)
    assert verify(digest, scored) is True
    _LEXICON["great"] = _LEXICON["great"] + 0.1
    try:
        assert sentiment.lexicon_vocab_sha() != digest.receipt.lexicon_vocab_sha
        assert verify(digest, scored) is False
    finally:
        _LEXICON["great"] = _LEXICON["great"] - 0.1
    assert verify(digest, scored) is True


def test_the_art_gate_passes_on_this_checkout():
    """The gate as a receipt, so pytest covers the front page too."""
    sys.path.insert(0, str(ROOT / "tools"))
    import check_repo_art
    receipt = check_repo_art.receipt()
    failed = [item["name"] for item in receipt["checks"] if not item["passed"]]
    assert not failed, failed
    assert receipt["passed"] is True
    assert len(receipt["outputs"]) == len(DRAWINGS)
