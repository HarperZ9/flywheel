"""unicode_guard falsifier.

Each class of text-spoof this module claims to neutralize, with a test that fails
if it does not. Plus the two properties that make it better than a silent bidi
replacer: the neutralization is recorded as a witnessed, digestible receipt
field, and clean text passes through byte-identical.
"""
from harness.unicode_guard import (
    NeutralizeResult, ThreatClass, is_clean, neutralize)


# --- clean text is untouched -------------------------------------------------

def test_plain_ascii_is_unchanged_and_clean():
    r = neutralize("git commit -m 'ship the thing'")
    assert r.sanitized == "git commit -m 'ship the thing'"
    assert not r.had_threats
    assert is_clean("rm build/ && python -m pytest")


def test_legitimate_non_ascii_single_script_is_clean():
    # A real Russian word (all Cyrillic) is not a mixed-script spoof.
    assert is_clean("привет мир")
    # A real accented Latin word is clean.
    assert is_clean("café résumé naïve")


# --- bidi (the Trojan-Source class) -----------------------------------------

def test_bidi_override_is_neutralized():
    text = "transfer‮" + "elttil" + "‬ to acct"
    r = neutralize(text)
    assert ThreatClass.BIDI_CONTROL.value in r.classes()
    assert "[U+202E]" in r.sanitized
    assert "‮" not in r.sanitized


def test_all_bidi_controls_flagged():
    for cp in (0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2066, 0x2069, 0x200F):
        r = neutralize("a" + chr(cp) + "b")
        assert r.had_threats, f"missed U+{cp:04X}"
        assert r.classes() == [ThreatClass.BIDI_CONTROL.value]


# --- zero-width / invisible --------------------------------------------------

def test_zero_width_joiner_is_neutralized():
    r = neutralize("pay​pal.com")
    assert ThreatClass.ZERO_WIDTH.value in r.classes()
    assert "[U+200B]" in r.sanitized


def test_soft_hyphen_and_bom_flagged():
    r = neutralize("ad­min﻿")
    classes = r.classes()
    assert ThreatClass.INVISIBLE.value in classes
    assert ThreatClass.ZERO_WIDTH.value in classes


# --- tag characters (the U+E00xx smuggling block) ---------------------------

def test_tag_characters_are_neutralized():
    text = "run" + "".join(chr(0xE0000 + c) for c in (0x41, 0x42))
    r = neutralize(text)
    assert ThreatClass.TAG_CHAR.value in r.classes()
    assert "\U000E0041" not in r.sanitized


# --- control characters ------------------------------------------------------

def test_c0_control_neutralized_but_tab_newline_kept():
    r = neutralize("line1\nline2\tend\x07bell")
    assert "\n" in r.sanitized
    assert "\t" in r.sanitized
    assert "[U+0007]" in r.sanitized
    assert ThreatClass.CONTROL_CHAR.value in r.classes()


# --- combining excess (Zalgo) ------------------------------------------------

def test_combining_excess_flagged():
    zalgo = "e" + "́" * 8
    r = neutralize(zalgo)
    assert ThreatClass.COMBINING_EXCESS.value in r.classes()


def test_a_few_combining_marks_are_allowed():
    # Two combining marks is normal (e.g. stacked accents), not Zalgo.
    assert is_clean("ẹ́")


# --- confusable / mixed script ----------------------------------------------

def test_cyrillic_homoglyph_in_latin_word_flagged():
    # "paypal" with a Cyrillic 'а' (U+0430) in place of ASCII 'a'.
    text = "pаypal"
    r = neutralize(text)
    assert ThreatClass.CONFUSABLE.value in r.classes()
    assert "[U+0430]" in r.sanitized


def test_greek_homoglyph_flagged():
    # Greek omicron (U+03BF) inside an otherwise-Latin token.
    text = "gοogle"
    r = neutralize(text)
    assert ThreatClass.CONFUSABLE.value in r.classes()


# --- normalization divergence ------------------------------------------------

def test_fullwidth_normalization_divergence_flagged():
    # Fullwidth Latin small letters normalize to ASCII under NFKC.
    text = "ｒｍ"  # fullwidth r m
    r = neutralize(text)
    assert ThreatClass.NORMALIZATION_DIVERGENCE.value in r.classes()
    assert r.nfkc == "rm"


def test_ligature_normalization_divergence_flagged():
    r = neutralize("ofﬁce")  # 'fi' ligature
    assert ThreatClass.NORMALIZATION_DIVERGENCE.value in r.classes()
    assert r.nfkc == "office"


# --- witnessed receipt field + determinism ----------------------------------

def test_receipt_field_shape_and_no_raw_text():
    text = "transfer‮elttil‬"
    r = neutralize(text)
    field = r.to_receipt_field()
    assert field["had_threats"] is True
    assert field["threat_count"] >= 1
    assert "bidi_control" in field["classes"]
    assert len(field["findings_digest"]) == 16
    # The receipt field carries a digest and counts, never the spoof text.
    import json
    dumped = json.dumps(field)
    assert "‮" not in dumped


def test_findings_digest_is_stable_across_calls():
    a = neutralize("pаypal​")
    b = neutralize("pаypal​")
    assert a.findings_digest() == b.findings_digest()


def test_clean_text_receipt_field_is_negative():
    r = neutralize("python -m pytest")
    f = r.to_receipt_field()
    assert f["had_threats"] is False
    assert f["threat_count"] == 0
    assert f["classes"] == []


def test_findings_sorted_by_position():
    r = neutralize("a​b‮c")
    positions = [f.position for f in r.findings]
    assert positions == sorted(positions)
