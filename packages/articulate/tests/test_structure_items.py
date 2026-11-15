"""List items under the structure rules, and the tier of a pronoun run.

Ten of 52 sampled replies carried a hand-back line and the pack caught two,
because most of them closed a bullet and the pack skipped lists. The pin,
pointer and landing rules now read a list item as a short paragraph. Each
case here has a near miss that differs by one feature, and the run rules
still stay out of lists.

A run of exactly three sentences on one personal pronoun was the largest
source of gating findings on human prose, and no sampled reply held one. It
reports at MEDIUM.
"""
import pytest

from articulate import rules_ext, structure_text
from test_pack_structure import SPECIMEN_B, hits, run, structure

ITEMS = [
    # landing: a hand-back that closes an item, or is the whole item
    ("structure-landing", "- **Listing.** Archiving keeps installs working but freezes the "
                          "listing. That one is your call.\n", ["HIGH"]),
    ("structure-landing", "- **Listing.** Archiving keeps installs working but freezes the "
                          "listing. That one is on the call sheet.\n", []),
    ("structure-landing", "- Whether to relicense the folder is up to you.\n", ["HIGH"]),
    ("structure-landing", "- Whether to relicense the folder turns on the audit.\n", []),
    ("structure-landing", "1. Granting the permission once adds each new record to your list "
                          "with no further step from anyone, and that click is yours.\n",
     ["HIGH"]),
    ("structure-landing", "1. Granting the permission once adds each new record to your list "
                          "with no further step from anyone, and that click is yours to make "
                          "whenever the next record is ready to go out.\n", []),
    ("structure-landing", "- [ ] The switch sits in the settings page.\n  That switch is "
                          "yours.\n", ["HIGH"]),
    ("structure-landing", "- Your call log is in the archive.\n- Their decision was final.\n",
     []),
    # pointer: a sentence in an item that only rates the one before it
    ("structure-pointer", "- The count came back at 40. That matters.\n", ["HIGH"]),
    ("structure-pointer", "- The count came back at 40. That matters to the two teams who "
                          "size their queues from it.\n", []),
    ("structure-pointer", "- Each team keeps its own copy. That is the silo.\n", ["MEDIUM"]),
    ("structure-pointer", "- This is the default.\n- That is the cache key.\n", []),
    # pin: an item that opens by announcing itself
    ("structure-pin", "- Here is the plan in short. We ship the fix on Monday, after the "
                      "cache test passes.\n", ["HIGH"]),
    ("structure-pin", "- Here is the plan.\n- Two steps remain.\n", []),
]


@pytest.mark.parametrize("category,text,tiers", ITEMS)
def test_list_item_control(category, text, tiers):
    assert [t for t, _r, _m in hits(text, category)] == tiers


def test_ordinary_list_items_stay_quiet():
    text = ("Install steps:\n\n"
            "- Download the archive for your platform.\n"
            "- Unpack it into a folder you can write to.\n"
            "- Run the installer. It asks for a folder and a port.\n"
            "- Open the settings page and choose a profile.\n"
            "1. The licence stays MIT.\n"
            "2. Keys open doors. Keys rust in rain. Keys get lost in coats.\n")
    assert structure(text) == []


def test_run_rules_stay_out_of_lists():
    text = "- Keys open doors.\n- Keys rust in rain.\n- Keys get lost in coats.\n"
    assert structure(text) == []
    text = "- Keys open doors. Keys rust in rain. Keys get lost in coats.\n"
    assert structure(text) == []


def test_a_list_item_span_indexes_the_text():
    text = "Notes:\n\n- **Listing.** Archiving freezes the listing. That one is your call.\n"
    (tier, rule, match), = hits(text, "structure-landing")
    assert (tier, rule, match) == ("HIGH", "structure-landing/handoff", "That one is your call.")
    f, = [f for f in run(text)["high"] if f["category"] == "structure-landing"]
    assert text[f["start"]:f["end"]] == match and f["line"] == 3


def test_a_wrapped_item_line_is_reported_once():
    text = "- The switch sits in the settings page.\n  That switch is yours.\n"
    assert len(hits(text, "structure-landing")) == 1


# --- a pronoun run of three reports, and does not gate ----------------------

PRONOUN = [
    ("It lives in small herds on the open plain, as far south as the islands near the "
     "cape. It is common across the whole of the temperate part of the continent. It "
     "runs from a rider at once when the herd has been hunted that season.\n", [("MEDIUM", "structure-anaphora/pronoun-run")]),
    ("I ran the suite twice on both machines. I read each failure against the log. I "
     "wrote the fix after lunch. I pushed it once the lock test passed.\n",
     [("HIGH", "structure-anaphora/run")]),
    ("One points at a line in the log. One reports that two counts agree. One hands "
     "the next step back.\n", [("HIGH", "structure-anaphora/run")]),
    ("Keys open doors. Keys rust in rain. Keys get lost in coats.\n",
     [("HIGH", "structure-anaphora/run")]),
]


@pytest.mark.parametrize("text,expected", PRONOUN)
def test_pronoun_run_tier(text, expected):
    assert [(t, r) for t, r, _m in hits(text, "structure-anaphora")] == expected


def test_a_pronoun_run_of_three_does_not_gate_and_is_no_triad():
    text = PRONOUN[0][0]
    r = run(text)
    assert r["gate"] == "ok" and r["verdict"] == "flagged"
    assert hits(text, "structure-triad") == []


def test_three_pronoun_sentences_on_one_frame_are_still_a_triad():
    text = "We read the file. We split the tokens. We print the errors.\n"
    assert [(t, r) for t, r, _m in hits(text, "structure-triad")] == [
        ("HIGH", "structure-triad/sentences")]
    assert run(text)["gate"] == "blocked"


def test_specimen_b_stays_blocked_with_its_opener_run_at_high():
    r = run(SPECIMEN_B)
    assert r["gate"] == "blocked"
    assert ("HIGH", "structure-anaphora/run") in [
        (t, rule) for t, rule, _m in hits(SPECIMEN_B, "structure-anaphora")]


# --- wrapped items and quoted hand-backs (found by checking the 0.19.0 notes) --

WRAPPED = ("- New rule pack, on under the chat profile and in the house voice\n"
           "  notes. A finding spans the whole run of sentences. The HIGH\n"
           "  findings gate under chat, and no other profile lists the pack.\n")


def test_the_wrapped_lines_of_an_item_are_not_read_as_a_paragraph():
    assert structure(WRAPPED) == [], "a line fragment under a marker is no paragraph"
    assert structure(WRAPPED.replace("\n  ", " ")) == [], "the same item on one line"


def test_a_hand_back_on_a_wrapped_line_is_reported_once_with_its_whole_span():
    text = ("- The switch sits in the settings page, and that\n"
            "  switch is yours.\n")
    found = structure(text)
    assert [(f["tier"], f["rule_id"]) for f in found] == [("HIGH", "structure-landing/handoff")]
    assert found[0]["match"] == "The switch sits in the settings page, and that\n  switch is yours."


def test_a_quoted_hand_back_is_a_mention():
    quoted = 'The bullet ended on "That one is your call." and on nothing else.\n'
    assert hits(quoted, "structure-landing") == []
    plain = ("That one is your call. The tests hold three cases of it in list items, "
             "and each has a near miss beside it.\n")
    assert [t for t, _r, _m in hits(plain, "structure-landing")] == ["MEDIUM"]


def test_a_full_stop_inside_a_quote_that_runs_on_does_not_end_the_sentence():
    text = ('His post reads "Keep the well. Water is patience. Water is memory. Water is '
            'care." and under his own profile no rule reports it.\n')
    assert structure(text) == [], "a quoted run is a mention inside one sentence"
    text = 'The note says (keys open doors.) and the rest of the page explains why.\n'
    prose = list(rules_ext.prose_lines(text.splitlines(keepends=True)))
    assert [len(unit) for unit in structure_text.paragraphs(prose)] == [1], (
        "a full stop inside a bracket that runs on in lower case")
    text = 'He said "Keys open doors." Keys rust in rain. Keys get lost in coats.\n'
    assert [t for t, _r, _m in hits(text, "structure-anaphora")] == ["LOW"], "a capital starts one"
