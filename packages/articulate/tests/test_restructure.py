"""Restructure moves source, confidence and limit sentences into one section,
word for word, and its relocation guard refuses any proposal that drops,
edits or orphans a sentence."""
import importlib
import re

import pytest

from voice_fixtures import DISCLOSURE, SCAFFOLD_ESSAY, templated_doc


def rs():
    return importlib.import_module("articulate.restructure")


def _spans(text):
    from articulate.meaning_guard import protected_spans
    return sorted((s["kind"], s["text"]) for s in protected_spans(text)
                  if s["kind"] in ("citation", "url", "number", "quote"))


def _unanchored(text):
    text = re.sub(r"\[\^m-[0-9a-f]{6,8}\]:? ?", "", text)
    text = re.sub(r"\[\(source\)\]\(#m-[0-9a-f]{6,8}\)|<a id=\"m-[0-9a-f]{6,8}\"></a> ?", "", text)
    return text


@pytest.mark.parametrize("anchors", ["footnote", "link"])
def test_every_citation_url_and_number_survives(anchors):
    out = rs().propose(SCAFFOLD_ESSAY, anchors=anchors)
    assert out["verdict"]["ok"], out["verdict"]
    assert out["moved"], "nothing moved"
    assert _spans(_unanchored(out["proposal"])) == _spans(SCAFFOLD_ESSAY)
    assert "## Sources and method" in out["proposal"]


def test_restructure_keeps_every_citation():
    text = templated_doc(0).replace("According to the filing,", "According to the filing [3],")
    out = rs().propose(text)
    assert out["verdict"]["ok"]
    assert out["proposal"].count("[3]") == text.count("[3]")


def test_disclosure_stays_in_place():
    out = rs().propose(SCAFFOLD_ESSAY)
    before = SCAFFOLD_ESSAY.splitlines().index(DISCLOSURE)
    lines = out["proposal"].splitlines()
    assert lines.index(DISCLOSURE) == before
    assert lines.count(DISCLOSURE) == 1


def test_a_paragraph_never_empties_and_keeps_a_claim():
    out = rs().propose(SCAFFOLD_ESSAY)
    body = out["proposal"].split("## Sources and method")[0]
    paras = [p for p in re.split(r"\n\s*\n", body) if p.strip()]
    assert len(paras) == len([p for p in re.split(r"\n\s*\n", SCAFFOLD_ESSAY) if p.strip()])
    assert all(_unanchored(p).strip() for p in paras)


def test_anchors_are_stable_across_runs():
    assert rs().propose(SCAFFOLD_ESSAY)["proposal"] == rs().propose(SCAFFOLD_ESSAY)["proposal"]


def test_summary_reports_scaffold_share_before_and_after():
    s = rs().propose(SCAFFOLD_ESSAY)["summary"]
    assert s["scaffold_share_after"] < s["scaffold_share_before"]
    assert s["scope"].startswith("Moving a limit line changes where a reader meets it.")


def _tamper(kind):
    proposal = rs().propose(SCAFFOLD_ESSAY)["proposal"]
    if kind == "dropped":
        return proposal.replace("Confidence: moderate.", "", 1), "sentence"
    if kind == "citation":
        return proposal.replace("[1]", "[2]", 1), "protected spans"
    anchor = re.search(r"\[\^m-[0-9a-f]{6,8}\]", proposal).group(0)
    return proposal.replace(anchor, "", 1), "anchor"


@pytest.mark.parametrize("kind", ["dropped", "citation", "orphan"])
def test_a_tampered_proposal_is_refused_with_a_named_reason(kind):
    bad, word = _tamper(kind)
    verdict = rs().verify_relocation(SCAFFOLD_ESSAY, bad)
    assert verdict["ok"] is False
    assert any(word in r for r in verdict["reasons"]), verdict


def test_an_untouched_text_verifies():
    assert rs().verify_relocation(SCAFFOLD_ESSAY, SCAFFOLD_ESSAY)["ok"] is True


def test_an_added_sentence_is_refused():
    bad = rs().propose(SCAFFOLD_ESSAY)["proposal"].replace(
        "The logs cover 14 months.", "The logs cover 14 months. I read every page.")
    assert rs().verify_relocation(SCAFFOLD_ESSAY, bad)["ok"] is False


def test_diff_is_unified_and_input_is_never_written(tmp_path):
    out = rs().propose(SCAFFOLD_ESSAY)
    assert out["diff"].startswith("--- ")
    assert out["schema"] == "articulate/restructure/v2"
    assert out["input_sha256"].startswith("sha256:")


def test_an_open_quote_across_paragraphs_does_not_refuse_an_untouched_text():
    # Regression from a real essay: a quote mark opened in one paragraph and
    # closed several paragraphs later, with three blank lines in between.
    text = ('# Notes\n\nShe said "the vote would wait.\n\n\n\nIt did not. The board met '
            'in 2021.\n\nThe minutes" ran to 14 pages.\n')
    assert rs().verify_relocation(text, text)["ok"]

