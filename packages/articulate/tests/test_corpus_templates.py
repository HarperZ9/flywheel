"""Sentence templates and rituals across one author's turns (Specimen C of
2026-11-15): a hand-back sentence that is ordinary once and a stamp by the
third turn. A single-passage check cannot see it; the series check can.
"""
from articulate import checkext, corpus, domains

LEADS = ["The branch is pushed and both machines are green.",
         "Nine of the forty lines failed on the second pass.",
         "Her note asks for the counterexamples and nothing else.",
         "The cache loader took the lock late on Tuesday.",
         "Three reviewers read the draft before noon.",
         "The parser now reads every line in the archive.",
         "A second run gave the same count as the first.",
         "The upload finished at four with no retries."]
HANDBACKS = ["A reply would go out in your name, so it is yours to write or approve.",
             "A reply in his name is his to write or approve.",
             "Mara's question about the support channel is yours to answer too.",
             "That click is yours.",
             "That switch is yours.",
             "That one is your call."]


def turns(lines, leads=LEADS):
    return [{"name": f"turn-{i + 1}", "text": f"{leads[i]} {line}\n"}
            for i, line in enumerate(lines)]


def found(docs, category):
    return [f for f in corpus.analyze_corpus(docs)["findings"] if f["category"] == category]


def test_each_handback_alone_passes_the_single_passage_check():
    """The fault is the repetition, so one turn raises no landing finding of
    the hand-back kind unless the sentence closes a paragraph."""
    text = "A reply in his name is his to write or approve. He has the draft from Monday.\n"
    r = checkext.check_text(text, profile=domains.load_profile("chat"))
    assert not [f for f in r["high"] if f["category"] == "structure-landing"]


def test_handback_template_is_reported_with_its_occurrences():
    hits = found(turns(HANDBACKS), "corpus/sentence-template")
    templates = {f["measure"]["template"]: f for f in hits}
    assert "is POSS to _" in templates, sorted(templates)
    f = templates["is POSS to _"]
    assert f["docs"] == ["turn-1", "turn-2", "turn-3"]
    assert [loc["excerpt"] for loc in f["locations"]] == HANDBACKS[:3]
    assert f["measure"]["docs"] == 3


def test_near_miss_two_turns_is_no_template():
    """One feature changed: the third turn says it another way."""
    lines = HANDBACKS[:2] + ["Mara asked about the support channel, and I have not answered her."]
    lines += ["The fourth run starts at noon.", "The fifth run starts at one."]
    assert not [f for f in found(turns(lines), "corpus/sentence-template")
                if "POSS" in f["measure"]["template"]]


def test_a_kept_phrase_is_protected_not_flagged():
    docs = turns(HANDBACKS)
    report = corpus.analyze_corpus(docs, keep=["is POSS to _"])
    assert not [f for f in report["findings"] if f["category"] == "corpus/sentence-template"
                and f["measure"]["template"] == "is POSS to _"]
    assert any(p["category"] == "corpus/sentence-template" for p in report["protected"])


def test_closing_ritual_is_reported():
    docs = [{"name": f"turn-{i + 1}",
             "text": f"{LEADS[i]}\n\nRunning now: the {w} worker and the site worker.\n"}
            for i, w in enumerate(["upload", "parser", "cache", "review"])]
    hits = found(docs, "corpus/ritual")
    assert [(f["measure"]["place"], f["measure"]["kind"], f["measure"]["shape"]) for f in hits] \
        == [("closing", "words", "running now"),
            ("closing", "skeleton", "_ now the _ and the _")]
    assert hits[0]["measure"]["docs"] == 4


def test_opening_ritual_is_reported_and_varied_openings_are_not():
    same = [{"name": f"turn-{i + 1}",
             "text": f"The {w} change is done and I confirmed it on the host.\n\n{LEADS[i]}\n"}
            for i, w in enumerate(["upload", "parser", "cache", "review"])]
    hits = found(same, "corpus/ritual")
    assert ("opening", "skeleton") in [(f["measure"]["place"], f["measure"]["kind"]) for f in hits]
    varied = [{"name": f"turn-{i + 1}", "text": f"{LEADS[i]}\n\n{LEADS[i + 4]}\n"} for i in range(4)]
    assert found(varied, "corpus/ritual") == []
