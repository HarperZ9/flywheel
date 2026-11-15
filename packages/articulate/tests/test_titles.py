"""The title workshop groups titles by skeleton and offers variants only from
the author's own one-line answer."""
import importlib
import re

import pytest


def titles():
    return importlib.import_module("articulate.titles")


SERIES = ["The Sandbox Was Never Just a Box", "The Summary Is Not The Record",
          "Verified Is Not Trustworthy", "The Timestamp Is Not the Order",
          "Availability Is Not Reach"]
CONTROLS = ["On the Duty of Civil Disobedience", "Self-Reliance", "Of Our Spiritual Strivings",
            "Southern Horrors: Lynch Law in All Its Phases", "The Modern Essay",
            "Corn-pone Opinions", "The Moral Equivalent of War", "The Brass Check",
            "Adversarial Interoperability", "The Scaling Hypothesis"]


def test_skeleton_keeps_closed_words_and_collapses_the_rest():
    assert titles().skeleton("The Sandbox Was Never Just a Box") == "the X was never just a X"


def test_the_five_negation_titles_share_one_family():
    fams = {titles().family(t) for t in SERIES}
    assert fams == {"X is not Y"}


@pytest.mark.parametrize("title,family", [
    ("Who Pays the Referees", "who/what/why X"),
    ("What the Formula Counts", "what the X verbs"),
    ("The Number Has a Vintage", "the X has/needs Y"),
    ("Growth Needs a Before", "the X has/needs Y"),
    ("The Terms for Telling", "the X of/for Y"),
    ("Models Propose, Oracles Dispose", "paired clause"),
    ("Rain and the Second Shift", "X and Y"),
    ("LTJ Bukem: The Man Behind the Atmosphere", "colon split"),
    ("Who Is Counting?", "question"),
    ("Borrowed Ground", "bare noun phrase"),
])
def test_mixed_titles_land_in_distinct_families(title, family):
    assert titles().family(title) == family


def test_control_titles_form_no_formula_family_of_three():
    report = titles().workshop(CONTROLS)
    assert not [f for f in report["families"] if f["formula"] and len(f["titles"]) >= 3]


def test_repeated_family_gets_a_question_and_no_variants_without_answers():
    report = titles().workshop(SERIES + ["Borrowed Ground"])
    fam = next(f for f in report["families"] if f["family"] == "X is not Y")
    assert fam["share"] == pytest.approx(5 / 6, abs=1e-3)
    assert len(report["questions"]) == 5
    assert all("friend" in q["question"] for q in report["questions"])
    assert report["suggestions"] == []


def _words(text):
    return {w.lower() for w in re.findall(r"[A-Za-z']+", text)}


def test_suggestions_use_only_answer_and_heading_words():
    answers = ["", "", "how a clean summary hides what the county left out of its minutes", "", ""]
    headings = [[], [], ["The minutes", "What the county kept"], [], []]
    report = titles().workshop(SERIES, answers=answers, headings=headings)
    sugg = report["suggestions"]
    assert sugg, "an answer gave no suggestion"
    allowed = _words(answers[2]) | _words(" ".join(headings[2]))
    for s in sugg:
        assert s["label"] == "suggestion"
        assert s["title"] == SERIES[2]
        assert _words(s["text"]) <= allowed, s
    assert len(sugg) <= 3


def test_suggestions_drop_a_family_already_used_twice():
    answers = ["the sandbox is not a box at all"] + [""] * 4
    report = titles().workshop(SERIES, answers=answers)
    assert all(s["family"] != "X is not Y" for s in report["suggestions"])


def test_workshop_reports_no_score_and_no_detector():
    report = titles().workshop(SERIES)
    assert report["ai_detector_consulted"] is False
    assert report["schema"] == "articulate/titles/v2"
    assert "score" not in report
