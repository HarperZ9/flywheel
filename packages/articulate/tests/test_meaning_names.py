"""Meaning-guard regressions for names and citations, and for formatting-only
edits the guard must let through.

Each unfaithful pair must read `changed` and each faithful pair `preserved`.
One test pins the blind spot the report states: a name used once, at a
sentence start, and swapped for another.
"""
import pytest

from articulate import invariants, meaning


def _verdict(original, rewrite):
    return meaning.compare(original, rewrite)["verdict"]


def _report(original, rewrite):
    return meaning.format_report(meaning.compare(original, rewrite))


# A name that opens with a lower-case letter was never an entity, a narrative
# citation had no pattern, and a name at a sentence start was weak even when
# the text used it mid-sentence too.
NAME_CHANGED = [
    ("It runs on macOS only.", "It runs on iOS only."),
    ("Test it on an iPhone first.", "Test it on an iPad first."),
    ("Smith (2020) showed the effect.", "Jones (2020) showed the effect."),
    ("Smith and Lee (2020, p. 4) showed it.", "Smith and Kim (2020, p. 4) showed it."),
    ("Alice approved the change. Ask Alice.", "Mallory approved the change. Ask Alice."),
    ("Alice approved the change.", "Mallory approved the change, as Mallory said."),
]
NAME_PRESERVED = [
    ("It runs on macOS only.", "Only macOS runs it."),
    ("Smith (2020) showed the effect.", "The effect was shown by Smith (2020)."),
    # A plain-language suggestion at a sentence start is a word swap.
    ("Utilize the cache first.", "Use the cache first."),
    # A title-case heading word is no evidence that the same word is a name.
    ("## Quick Start\n\nStart the server.", "## Quick Start\n\nLaunch the server."),
    # A word the text also uses in lower case is an ordinary word.
    ("Start the job. We start it daily, per the Start page.",
     "Run the job. We start it daily, per the Start page."),
]


@pytest.mark.parametrize("original,rewrite", NAME_CHANGED)
def test_changed_name_is_caught(original, rewrite):
    assert _verdict(original, rewrite) == "changed", _report(original, rewrite)


@pytest.mark.parametrize("original,rewrite", NAME_PRESERVED)
def test_kept_name_is_preserved(original, rewrite):
    assert _verdict(original, rewrite) == "preserved", _report(original, rewrite)


def test_single_sentence_start_name_swap_is_a_documented_blind_spot():
    """A capitalized word that opens a sentence may be an ordinary word, and
    pairing two of them by the word that follows refuses plain rewrites such as
    "Utilize the cache" to "Use the cache". A name used once at a sentence start
    therefore goes unreported, and the report says so."""
    report = meaning.compare("Alice approved the change.", "Mallory approved the change.")
    assert report["verdict"] == "preserved"
    assert "opens a sentence" in report["scope"]


# The compare path keyed each citation and quote on its raw text, so a
# formatting-only edit read as a change. fix and polish mask these spans and
# restore them byte for byte, so this reached `articulate compare`, the MCP
# compare tool, and a hand edit gated with --gate.
FORMAT_PRESERVED = [
    ("It holds (Smith, 2020).", "It holds (Smith 2020)."),
    ("It holds (Smith et al., 2020).", "It holds (Smith et al. 2020)."),
    ("It holds [1-3].", "It holds [1\u20133]."),
    ("It holds [1, 2].", "It holds [1,2]."),
    ("It holds (Smith & Lee, 2020).", "It holds (Smith and Lee, 2020)."),
    ('She said "ship it" today.', "She said \u201cship it\u201d today."),
    ('She said "don\'t ship" today.', "She said \u201cdon\u2019t ship\u201d today."),
]
FORMAT_CHANGED = [
    ("It holds (Smith, 2020).", "It holds (Smith, 2021)."),
    ("It holds [1-3].", "It holds [1-4]."),
    ("It holds [1, 2].", "It holds [12]."),
    ('She said "ship it" today.', "She said \u201cship it now\u201d today."),
]


@pytest.mark.parametrize("original,rewrite", FORMAT_PRESERVED)
def test_formatting_only_citation_or_quote_edit_is_preserved(original, rewrite):
    assert _verdict(original, rewrite) == "preserved", _report(original, rewrite)


@pytest.mark.parametrize("original,rewrite", FORMAT_CHANGED)
def test_changed_citation_or_quote_is_caught(original, rewrite):
    assert _verdict(original, rewrite) == "changed", _report(original, rewrite)


def test_normalized_key_keeps_the_written_text():
    report = meaning.compare("It holds (Smith, 2020).", "It holds (Smith 2020).")
    row = next(r for r in report["items"] if r["kind"] == "citation")
    assert (row["before"]["text"], row["after"]["text"]) == ("(Smith, 2020)", "(Smith 2020)")


# The plain-language pack suggests "under" for "pursuant to" and "in accordance
# with". Before a statute cited title first, the title number read as a count,
# so "under 5 U.S.C. 552" was a bound and the pack's own suggestion was refused.
STATUTE_PRESERVED = [
    ("Pursuant to 5 U.S.C. 552, we publish it.", "Under 5 U.S.C. 552, we publish it."),
    ("We act in accordance with 21 CFR Part 11.", "We act under 21 CFR Part 11."),
    ("They are kept pursuant to 45 C.F.R. 164.512(b).",
     "They are kept under 45 C.F.R. 164.512(b)."),
]
STATUTE_CHANGED = [
    ("Under 5 U.S.C. 552, we publish it.", "Under 5 U.S.C. 553, we publish it."),
    ("We act under 21 CFR Part 11.", "We act under 21 CFR Part 12."),
]


@pytest.mark.parametrize("original,rewrite", STATUTE_PRESERVED)
def test_statute_citation_is_no_bound(original, rewrite):
    assert _verdict(original, rewrite) == "preserved", _report(original, rewrite)


@pytest.mark.parametrize("original,rewrite", STATUTE_CHANGED)
def test_changed_statute_citation_is_caught(original, rewrite):
    assert _verdict(original, rewrite) == "changed", _report(original, rewrite)


def test_statute_citation_is_one_span():
    text = "Under 5 U.S.C. § 552(b)(6), see 85 Fed. Reg. 1234 and 124 Stat. 2861."
    items = invariants.extract(text)
    assert [i["text"] for i in items if i["kind"] == "citation"] == [
        "5 U.S.C. § 552(b)(6)", "85 Fed. Reg. 1234", "124 Stat. 2861"]
    assert [i for i in items if i["kind"] in ("number", "scope")] == []
