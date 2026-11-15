"""The claims, product-copy and note packs, each with a positive case, a
negative case and a control sentence that must not be flagged, plus degraded
inputs that must not read as a pass."""
import pytest

from articulate import checkext, domains, pack_claims


def _cats(text, profile):
    r = checkext.check_text(text, profile=domains.load_profile(profile))
    return r, [f["category"] for f in r["high"] + r["medium"] + r["low"]]


# claims (R3, with the PU30-40 denominator)

def test_a_claim_with_no_evidence_is_reported_with_its_denominator():
    r, cats = _cats("Articulate is 10x faster than Vale. Try it today.", "product-copy")
    assert cats.count("claim-without-evidence") == 1
    label = [f for f in r["low"] if f["category"] == "claim-without-evidence"][0]["label"]
    assert "0 of 1 claim sentences" in label


def test_a_claim_that_points_at_its_evidence_is_not_reported():
    text = ("Articulate is 10x faster than Vale on 75 texts. The run is in "
            "`bench/results.json`.")
    _r, cats = _cats(text, "product-copy")
    assert "claim-without-evidence" not in cats
    cov = pack_claims.coverage(text)
    assert (cov["claims"], cov["bound"], cov["unbound_lines"]) == (1, 1, [])


def test_an_ordinary_sentence_with_first_and_only_is_not_a_claim():
    _r, cats = _cats("I read the log first, and only then ran the tests again.", "product-copy")
    assert "claim-without-evidence" not in cats


@pytest.mark.parametrize("text", ["", "   \n\n", "```\nfastest tool\n```\n", "<!-- -->\n"])
def test_degraded_input_reports_no_coverage(text):
    cov = pack_claims.coverage(text)
    assert cov["claims"] == 0 and cov["bound"] == 0 and cov["unbound_lines"] == []


# product-copy (R15, R16)

def test_a_maker_side_lead_is_reported():
    _r, cats = _cats("I built this tool because nothing else checked my essays.\n", "product-copy")
    assert "lead-author-framed" in cats


def test_a_lead_about_what_the_tool_lacks_is_reported():
    _r, cats = _cats("Articulate is not a detector and does not score authorship.\n",
                     "product-copy")
    assert "lead-author-framed" in cats


def test_a_reader_facing_lead_is_not_reported():
    _r, cats = _cats("Articulate checks prose on your computer and names each pattern with "
                     "its line.\n\nI built it for my own essays.\n", "product-copy")
    assert "lead-author-framed" not in cats


def _long(body):
    return "# Tool\n\n" + " ".join(["It reads each file and names the line."] * 25) + body


def test_a_long_page_with_no_mission_is_reported():
    _r, cats = _cats(_long(""), "product-copy")
    assert "mission-missing" in cats


def test_a_mission_heading_or_line_clears_the_finding():
    _r, cats = _cats(_long("\n\n## Why it exists\n\nTo make checking cheap.\n"), "product-copy")
    assert "mission-missing" not in cats
    _r, cats = _cats(_long("\n\nIts mission is to make truth cheap to check.\n"), "product-copy")
    assert "mission-missing" not in cats


def test_a_short_page_needs_no_mission_line():
    _r, cats = _cats("Articulate checks prose on your computer.\n", "product-copy")
    assert "mission-missing" not in cats


def test_product_copy_keeps_the_authors_terms_and_freezes_them_in_edits():
    prof = domains.load_profile("product-copy")
    for term in ("metamers", "lens", "make truth cheap to check"):
        assert term in prof["keep"] and term in prof["freeze_terms"]


# note (R7)

def test_a_stock_opener_and_closing_offer_gate_a_note():
    r, cats = _cats("I hope this finds you well. The draft is attached. Let me know if you "
                    "have any questions.", "note")
    assert {"note-opener", "note-closing-offer"} <= set(cats)
    assert r["gate"] == "blocked"


def test_a_short_direct_note_passes():
    r, cats = _cats("Hey Sam, the draft's in your inbox. Tear it apart, I can take it.", "note")
    assert r["gate"] == "ok" and not [c for c in cats if c.startswith("note-")]


def test_hope_about_something_else_is_not_an_opener():
    r, cats = _cats("I hope the rain holds off for your drive tomorrow.", "note")
    assert "note-opener" not in cats and r["gate"] == "ok"


def test_office_words_and_length_report_without_gating():
    long_note = "Regarding the draft, it is done. " + "The second part reads fine now. " * 30
    r, cats = _cats(long_note, "note")
    assert "note-professional" in cats and "note-length" in cats
    assert r["gate"] == "ok"
