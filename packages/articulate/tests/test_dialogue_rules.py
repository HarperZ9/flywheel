"""The dialogue profile: each check fires on its shape and leaves plain speech alone."""
from pathlib import Path

import pytest

from articulate import dialogue_parse, dialogue_rules

FIXTURE = Path(__file__).parent / "data" / "dialogue" / "pygmalion-act2.txt"


def checks(text, themes=(), proper=frozenset()):
    return {f["check"] for f in dialogue_rules.check_line(text, themes, proper)}


# A line in the shape the author rejected on 2026-10-21, rewritten with new words.
MODEL_LINE = "You want me cruel. Cruel is easy; anyone could prove it. I am logic."


def test_the_rejected_shape_is_caught_three_ways():
    assert {"epigram-semicolon", "epigram-definition", "closing-zinger"} <= checks(MODEL_LINE)


@pytest.mark.parametrize("line", [
    "All right. All right, then.",
    "Tide's on the turn. I can feel it in the backs of my legs, like a dog wanting out.",
    "Glass is glass. She doesn't know the difference. Ships might.",
    "No. No, no. Not the stairs. Not tonight.",
    "I counted them. I counted them going up, and I count them now.",
    "Get your hand off. That's my good coat. My only one.",
    "Feet first, and the lantern after on a line. Everybody knows that.",
])
def test_plain_broken_and_repetitive_speech_is_not_flagged(line):
    assert checks(line) == set()


def test_contrast_pair():
    assert "contrast-pair" in checks("We do not call it broken. We call it opened.")
    assert "contrast-pair" not in checks("We do not know. They went out at nine.")


def test_antithesis_from_the_prose_detector():
    assert "antithesis" in checks("It's not just a lamp, it's the town's conscience.")
    assert "antithesis" not in checks("Not now. Come back at ten.")


def test_semicolon_antithesis_needs_balance_and_a_pivot():
    assert "epigram-semicolon" in checks("If you drink, you die; if you don't drink, you die.")
    # A semicolon that only joins two plain clauses is punctuation, not an epigram.
    assert "epigram-semicolon" not in checks("Go to bed, dear; and don't think of them.")


def test_definition_of_an_abstraction():
    assert "epigram-definition" in checks("Mercy is a tide.")
    assert "epigram-definition" in checks("I am arithmetic.")
    # A name is not an abstraction, so a fact about a lamp is not a definition.
    assert "epigram-definition" not in checks("Mother is dark.", proper=frozenset({"Mother"}))
    assert "epigram-definition" not in checks("The tide is out.")


def test_maxim_is_a_general_rule_not_an_event():
    assert "epigram-maxim" in checks("No married man is ever attractive except to his wife.")
    assert "epigram-maxim" in checks("One draws on it.")
    assert "epigram-maxim" not in checks("Nobody's ever measured.")
    assert "epigram-maxim" not in checks("Nobody was on the quay at nine.")


def test_in_a_here_comparison():
    assert "epigram-here" in checks("In Hesk they count the money. Here we count the tide.")
    assert "epigram-here" not in checks("In the morning, then. I'll be on the quay.")


def test_theme_statement_needs_a_theme_word_and_a_general_claim():
    themes = ["truth", "fault"]
    assert "theme-statement" in checks("Nobody tells the truth in a fog.", themes)
    assert "theme-statement" not in checks("She told me the truth at nine.", themes)
    assert "theme-statement" not in checks("Nobody tells the truth in a fog.")


def test_closing_zinger_is_a_short_aphoristic_end():
    long_then_short = ("I have walked the floor every low water for twenty years and I have "
                       "never once found what I was sent for. Hope is cheap.")
    assert "closing-zinger" in checks(long_then_short)
    assert "closing-zinger" not in checks("I walked the floor for an hour and found nothing. "
                                          "Then I went home.")


def test_abstract_density():
    assert "abstract-density" in checks("Your conscience and your loyalty are a liability.")
    assert "abstract-density" not in checks("Your coat and your hat are on the hook.")


def test_human_dialogue_is_mostly_left_alone():
    lines = dialogue_parse.parse(FIXTURE.read_text(encoding="utf-8"), FIXTURE.name)
    assert len(lines) >= 40
    proper = dialogue_rules.proper_nouns(lines)
    flagged = [r for r in lines if dialogue_rules.check_line(r["text"], (), proper)]
    # Shaw is a talker; the calibration rate over the whole play is about 2 percent.
    assert len(flagged) <= 4, [r["text"][:60] for r in flagged]


def test_weights_cover_every_check():
    assert set(dialogue_rules.EPIGRAM_CHECKS) <= set(dialogue_rules.WEIGHTS)
    found = dialogue_rules.check_line(MODEL_LINE)
    assert all(f["weight"] == dialogue_rules.WEIGHTS[f["check"]] for f in found)
