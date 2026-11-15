"""Controlled English: sentence length, one instruction per sentence, idioms,
phrasal verbs, and sentence-initial pronouns with no noun. Positive, negative,
and an option or gate control for each rule.
"""
import pytest

from articulate import checkext, domains, profiles


def _run(text, **opts):
    prof = domains.load_profile("controlled-english")
    if opts:
        prof = dict(prof, options={"controlled-english": opts})
    return checkext.check_text(text, profile=prof)


def _hits(text, cat, **opts):
    r = _run(text, **opts)
    return [f for f in r["high"] + r["medium"] + r["low"] if f["category"] == cat]


LONG_DESCRIPTION = "The " + " ".join(["valve"] * 26) + " closes.\n"   # 28 words
LONG_INSTRUCTION = "Remove the " + " ".join(["small"] * 18) + " cover.\n"  # 21 words
MID_DESCRIPTION = "The " + " ".join(["small"] * 19) + " cover closes.\n"  # 22 words


def test_sentence_length_tiers():
    assert [f["tier"] for f in _hits(LONG_DESCRIPTION, "controlled-sentence-length")] == ["MEDIUM"]
    assert [f["tier"] for f in _hits(LONG_INSTRUCTION, "controlled-sentence-length")] == ["LOW"]
    assert _hits(MID_DESCRIPTION, "controlled-sentence-length") == []


def test_sentence_length_gates_and_is_an_option():
    assert _run(LONG_DESCRIPTION)["gate"] == "blocked"
    assert _hits(LONG_DESCRIPTION, "controlled-sentence-length", max_description_words=40) == []
    assert _hits(LONG_INSTRUCTION, "controlled-sentence-length", max_instruction_words=30) == []


@pytest.mark.parametrize("text,flagged", [
    ("Open the panel and remove the cover.", True),
    ("Open the panel, then remove the cover.", True),
    ("Open the panel.", False),
    ("The panel and the cover are steel.", False),
])
def test_one_instruction_per_sentence(text, flagged):
    assert bool(_hits(text + "\n", "controlled-multi-instruction")) is flagged


def test_idiom_with_literal_form():
    hit = _hits("It works out of the box.\n", "controlled-idiom")
    assert len(hit) == 1 and "'by default'" in hit[0]["label"]
    assert _hits("It works by default.\n", "controlled-idiom") == []


def test_phrasal_verb_with_single_word():
    hit = _hits("Find out the version first.\n", "controlled-phrasal-verb")
    assert len(hit) == 1 and "'learn'" in hit[0]["label"]
    assert _hits("Learn the version first.\n", "controlled-phrasal-verb") == []


@pytest.mark.parametrize("text,flagged", [
    ("This allows retries.", True),
    ("It prevents a restart.", True),
    ("This setting allows retries.", False),
    ("The setting allows retries. It is on by default.", True),
])
def test_vague_pronoun(text, flagged):
    assert bool(_hits(text + "\n", "controlled-vague-pronoun")) is flagged


def test_low_rules_report_without_blocking():
    assert _run("This allows retries. Find out the version.\n")["gate"] == "ok"
