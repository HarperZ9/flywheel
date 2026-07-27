"""The Phase 2 report-only checks: counted, never hard, in every slop level."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import check_writing as CW  # noqa: E402
import writing_profiles as WP  # noqa: E402


def test_passive_voice_is_counted():
    r = CW.check_text("The file is read by the parser.", WP.load("readme"))
    assert r["violations"].get("passive_voice", 0) >= 1


def test_irregular_participle_passive_is_counted():
    r = CW.check_text("The report was written yesterday.", WP.load("readme"))
    assert r["violations"].get("passive_voice", 0) >= 1


def test_active_voice_is_not_flagged():
    r = CW.check_text("The parser reads the file.", WP.load("readme"))
    assert "passive_voice" not in r["violations"]


def test_ing_main_verb_is_counted():
    r = CW.check_text("The tool is running the checks.", WP.load("readme"))
    assert r["violations"].get("ing_main_verb", 0) >= 1


def test_nominalization_verb_form_is_counted():
    r = CW.check_text("We perform analysis of the log.", WP.load("readme"))
    assert r["violations"].get("nominalization", 0) >= 1


def test_nominalization_suffix_before_of_is_counted():
    r = CW.check_text("The utilization of memory grew.", WP.load("readme"))
    assert r["violations"].get("nominalization", 0) >= 1


def test_plain_of_phrase_is_not_a_nominalization():
    r = CW.check_text("The top of the file holds imports.", WP.load("readme"))
    assert "nominalization" not in r["violations"]


def test_long_paragraph_is_counted():
    para = " ".join(f"Sentence number {i} sits here." for i in range(8))
    r = CW.check_text(para, WP.load("readme"))
    assert r["violations"].get("long_paragraph", 0) == 1


def test_two_short_paragraphs_are_not_flagged():
    text = "One sentence.\n\nAnother sentence."
    r = CW.check_text(text, WP.load("readme"))
    assert "long_paragraph" not in r["violations"]


def test_the_new_checks_are_never_hard_in_any_slop_level():
    text = ("The file is read by the parser. The tool is running checks. "
            "We perform analysis of the log. "
            + " ".join(f"Filler sentence {i} here." for i in range(8)))
    for profile_name in ("procedure", "readme", "narrative"):
        r = CW.check_text(text, WP.load(profile_name))
        for cat in ("passive_voice", "ing_main_verb", "nominalization",
                    "long_paragraph"):
            assert cat not in r["hard"], (profile_name, cat)


def test_hard_by_slop_never_contains_the_report_only_categories():
    report_only = {"passive_voice", "ing_main_verb", "nominalization",
                   "long_paragraph"}
    for level, cats in CW.HARD_BY_SLOP.items():
        assert not (cats & report_only), level


def test_regular_ed_participle_passive_is_counted():
    r = CW.check_text("The bug was fixed by the patch.", WP.load("readme"))
    assert r["violations"].get("passive_voice", 0) >= 1


def test_gerund_without_be_is_not_an_ing_main_verb():
    r = CW.check_text("Running helps the tests.", WP.load("readme"))
    assert "ing_main_verb" not in r["violations"]


def test_long_paragraph_boundary_six_passes_seven_flags():
    six = " ".join(f"Sentence {i} here." for i in range(6))
    seven = " ".join(f"Sentence {i} here." for i in range(7))
    assert "long_paragraph" not in CW.check_text(six, WP.load("readme"))["violations"]
    assert CW.check_text(seven, WP.load("readme"))["violations"].get(
        "long_paragraph", 0) == 1


def test_report_only_counts_do_not_move_the_headline_number():
    prof = WP.load("readme")
    clean = CW.check_text("The parser reads files.", prof)
    noisy = CW.check_text("The file is read by the parser.", prof)
    assert noisy["total"] == clean["total"] == 0
    assert noisy["report_total"] >= 1
    assert noisy["per100w"] == 0.0
    assert noisy["report_per100w"] > 0.0
