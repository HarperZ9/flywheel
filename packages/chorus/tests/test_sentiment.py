from chorus.item import DiscourseItem
from chorus.sentiment import score, score_text, lexicon_vocab_sha, LEXICON_VERSION


def _item(text, eng=0):
    return DiscourseItem("i", "video", "v", None, "a", text, eng, None, {})


def test_positive_and_negative_have_expected_sign():
    assert score_text("this is great, I love it")[0] > 0.2
    assert score_text("this is terrible, I hate it")[0] < -0.2


def test_negation_flips_sign():
    pos, _ = score_text("good")
    neg, _ = score_text("not good")
    assert pos > 0 and neg < 0


def test_intensifier_increases_magnitude():
    base, _ = score_text("good")
    strong, _ = score_text("very good")
    assert strong > base


def test_neutral_text_is_near_zero_and_evidence_is_empty():
    compound, evidence = score_text("the meeting is at three")
    assert abs(compound) < 0.1 and evidence == ()


def test_score_wraps_items_with_lexicon_provenance():
    out = score([_item("wonderful"), _item("awful")])
    assert out[0].provenance == "lexicon" and out[0].compound > 0
    assert out[1].compound < 0


def test_vocab_hash_is_stable_and_versioned():
    assert LEXICON_VERSION
    assert lexicon_vocab_sha() == lexicon_vocab_sha() and len(lexicon_vocab_sha()) == 16
