"""Corpus mode names patterns that only show across a series, with locations.

The templated fixture repeats one paragraph shape, one heading set, one phrase
and one title formula across four documents. Each category must fire on it at
the line where the pattern sits. The varied fixture must fire none, which is
the control showing the categories do not fire on any four short pieces.
"""
import pytest

from voice_fixtures import templated_docs, varied_docs, TEMPLATED_TITLES

def _corpus():
    import importlib
    return importlib.import_module("articulate.corpus")


CATEGORIES = ["corpus/title-formula", "corpus/shared-ngram", "corpus/shared-construction",
              "corpus/paragraph-scaffold", "corpus/section-symmetry", "corpus/rhythm",
              "corpus/perspective", "corpus/abstract-run", "corpus/sentence-template",
              "corpus/ritual"]


def _by_category(report):
    out = {}
    for f in report["findings"]:
        out.setdefault(f["category"], []).append(f)
    return out


def test_templated_series_triggers_every_category():
    report = _corpus().analyze_corpus(templated_docs())
    found = _by_category(report)
    assert sorted(found) == sorted(CATEGORIES)


def test_every_finding_has_the_shared_record_shape():
    report = _corpus().analyze_corpus(templated_docs())
    for f in report["findings"]:
        assert set(f) == {"category", "docs", "locations", "measure", "reader_cost",
                          "direction", "scope", "protected"}
        assert f["locations"], f["category"]
        for loc in f["locations"]:
            assert set(loc) == {"doc", "line_start", "line_end", "excerpt"}
            assert 1 <= loc["line_start"] <= loc["line_end"]
        assert f["reader_cost"] and f["direction"] and f["scope"]
        assert f["protected"] is False


def test_findings_point_at_the_right_lines():
    docs = templated_docs()
    found = _by_category(_corpus().analyze_corpus(docs))
    lines = docs[0]["text"].splitlines()
    scaffold = [l for f in found["corpus/paragraph-scaffold"] for l in f["locations"]
                if l["doc"] == "t0.md"]
    assert scaffold and all(lines[l["line_start"] - 1].startswith("The ledger shows") for l in scaffold)
    ngram = found["corpus/shared-ngram"][0]
    assert "oversight board approved the funding" in ngram["measure"]["gram"]
    loc = next(l for l in ngram["locations"] if l["doc"] == "t0.md")
    assert "oversight board" in lines[loc["line_start"] - 1]
    title = found["corpus/title-formula"][0]
    assert title["measure"]["family"] == "X is not Y"
    assert sorted(title["measure"]["titles"]) == sorted(TEMPLATED_TITLES)
    assert all(l["line_start"] == 1 for l in title["locations"])
    heads = [f for f in found["corpus/section-symmetry"] if f["measure"].get("kind") == "heading-overlap"]
    assert any(l["excerpt"] == "## In short" for f in heads for l in f["locations"])


def test_varied_series_triggers_nothing():
    report = _corpus().analyze_corpus(varied_docs())
    assert report["findings"] == [], [(f["category"], f["measure"]) for f in report["findings"]]


def test_keep_listed_refrain_is_counted_and_not_flagged():
    report = _corpus().analyze_corpus(templated_docs(), keep=["In short"])
    flagged = [l["excerpt"] for f in report["findings"] for l in f["locations"]]
    assert "## In short" not in flagged
    assert any(p["text"].lower() == "in short" for p in report["protected"])


def test_front_matter_keep_list_is_honored():
    docs = templated_docs()
    docs[0]["text"] = "---\narticulate-keep: In short\n---\n" + docs[0]["text"]
    report = _corpus().analyze_corpus(docs)
    assert any(p["text"].lower() == "in short" for p in report["protected"])


def test_report_carries_no_score_and_says_no_detector_was_consulted():
    report = _corpus().analyze_corpus(templated_docs())
    assert report["ai_detector_consulted"] is False
    assert not {"score", "humanness", "human_score", "ai_probability"} & set(report)
    assert "shows where each pattern occurs" in report["scope"]


def test_single_document_mode_runs_structural_checks():
    report = _corpus().analyze_corpus(templated_docs()[:1], single=True)
    cats = {f["category"] for f in report["findings"]}
    assert "corpus/paragraph-scaffold" in cats and "corpus/perspective" in cats
    assert "corpus/shared-ngram" not in cats


def test_two_documents_are_required_without_single():
    with pytest.raises(ValueError):
        _corpus().analyze_corpus(templated_docs()[:1])


def test_title_resolution_order():
    c = _corpus()
    assert c.doc_title({"name": "a", "text": "# Heading\n", "title": "Given"}) == "Given"
    assert c.doc_title({"name": "a", "text": "---\ntitle: Front\n---\n# Heading\n"}) == "Front"
    assert c.doc_title({"name": "a", "text": "Intro.\n\n# Heading\n"}) == "Heading"
    assert c.doc_title({"name": "a", "text": "<html><title>Page</title></html>"}) == "Page"


def test_text_report_names_each_category_with_its_location():
    c = _corpus()
    text = c.format_report(c.analyze_corpus(templated_docs()))
    for cat in CATEGORIES:
        assert cat in text
    assert "t0.md:" in text
    assert "—" not in text


def test_disclosure_lines_are_always_protected():
    docs = templated_docs()
    for d in docs:
        d["text"] += "\nDrafted with Claude from the public record and checked by the editor.\n"
    report = _corpus().analyze_corpus(docs)
    grams = [f["measure"].get("gram", "") for f in report["findings"]
             if f["category"] == "corpus/shared-ngram"]
    assert not any("public record and checked" in g for g in grams)
    assert any("Drafted with Claude" in p["text"] for p in report["protected"])
