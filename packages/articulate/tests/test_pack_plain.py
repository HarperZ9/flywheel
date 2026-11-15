"""The plain-language pack: the readability gate, long sentences, and wordy
phrases. The corpus samples give a hard text and a plain one; options show that
each limit is a setting and that the gate needs enough words to be meaningful.
"""
import os

import pytest

from articulate import checkext, domains, pack_plain, pack_util, profiles

_CORPUS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "corpus", "domains", "plain-language")


def _text(name):
    with open(os.path.join(_CORPUS, name), encoding="utf-8") as fh:
        return fh.read()


def _run(text, **opts):
    prof = domains.load_profile("plain-language")
    if opts:
        prof = dict(prof, options={"plain-language": opts})
    return checkext.check_text(text, profile=prof)


def _cats(text, **opts):
    r = _run(text, **opts)
    return [f["category"] for f in r["high"] + r["medium"] + r["low"]]


def test_hard_text_fails_the_readability_gate():
    r = _run(_text("flagged.md"))
    hit = [f for f in r["medium"] if f["category"] == "plain-readability"]
    assert len(hit) == 1 and "above the target 8" in hit[0]["label"]
    assert r["gate"] == "blocked"


def test_plain_text_passes():
    r = _run(_text("clean.md"))
    assert "plain-readability" not in _cats(_text("clean.md")) and r["gate"] == "ok"


def test_target_is_an_option():
    assert "plain-readability" not in _cats(_text("flagged.md"), max_grade=30.0)


def test_short_text_is_below_the_word_floor():
    hard = ("Notwithstanding administrative considerations, comprehensive documentation "
            "verification necessitates institutional authentication procedures.\n")
    assert "plain-readability" not in _cats(hard)
    assert "plain-readability" in _cats(hard, min_words=5)


def test_formula_matches_flesch_kincaid():
    grade, ease = pack_plain.grade_and_ease(1, 10, 15)
    assert round(grade, 2) == 6.01 and round(ease, 3) == 69.785


@pytest.mark.parametrize("word,count", [
    ("cat", 1), ("table", 2), ("people", 2), ("beautiful", 3), ("application", 4),
    ("readability", 5), ("jumped", 1), ("wanted", 2), ("boxes", 2), ("agree", 2),
])
def test_syllable_estimate(word, count):
    assert pack_util.syllables(word) == count


def test_long_sentence():
    long_one = "We " + " ".join(["check"] * 28) + " it.\n"
    assert "plain-long-sentence" in _cats(long_one)
    assert "plain-long-sentence" not in _cats("We check it twice.\n")
    assert "plain-long-sentence" not in _cats(long_one, max_sentence_words=40)


def test_wordy_phrases_carry_a_suggestion():
    r = _run("We will commence the work in order to test it.\n")
    wordy = [f for f in r["low"] if f["category"] == "plain-wordy"]
    assert [f["match"] for f in wordy] == ["commence", "in order to"]
    assert "'start'" in wordy[0]["label"]
    assert "plain-wordy" not in _cats("We will start the commencement work to test it.\n")
