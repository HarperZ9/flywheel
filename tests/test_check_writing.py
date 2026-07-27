import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import check_writing as CW  # noqa: E402
import writing_profiles as WP  # noqa: E402


def test_strip_code_removes_fenced_blocks():
    t = "before\n```python\nx = 1  # utilize leverage\n```\nafter"
    out = CW.strip_code(t)
    assert "utilize" not in out
    assert "before" in out and "after" in out


def test_strip_code_removes_inline_backticks_and_math():
    assert "utilize" not in CW.strip_code("run `utilize()` now")
    assert "alpha" not in CW.strip_code("the value $\\alpha$ holds")


def test_sentences_split_on_terminal_punctuation_only():
    t = "One sentence wraps\nacross a line. Two is here! Three?"
    s = CW.sentences(t)
    assert len(s) == 3
    assert "wraps across a line" in s[0]


def test_count_words_counts_word_tokens():
    assert CW.count_words("one two three") == 3
    assert CW.count_words("code `ignored` after strip is on caller") == 7


def test_marketing_word_is_a_violation_and_hard_in_flavored():
    prof = WP.load("readme")
    r = CW.check_text("This is a seamless and powerful tool.", prof)
    assert r["violations"].get("marketing_adjective", 0) >= 2
    assert "marketing_adjective" in r["hard"]


def test_banned_slop_word_is_counted():
    prof = WP.load("research")
    r = CW.check_text("We utilize the system to facilitate output.", prof)
    assert r["violations"].get("banned_word", 0) >= 2


def test_em_dash_is_hard_where_the_profile_bans_it():
    prof = WP.load("research")
    r = CW.check_text("This is a clause - and another.".replace("-", "—"), prof)
    assert r["em_dash"] == 1
    assert "em_dash" in r["hard"]


def test_narrative_profile_never_flags_em_dash():
    prof = WP.load("narrative")
    r = CW.check_text("A long dash lives here" + "—" + "and stays.", prof)
    assert r["em_dash"] == 1
    assert "em_dash" not in r["hard"]


def test_contraction_and_semicolon_hard_only_in_strict():
    strict = WP.load("procedure")
    flav = WP.load("readme")
    text = "Don't stop; keep going."
    assert "contraction" in CW.check_text(text, strict)["hard"]
    assert "semicolon" in CW.check_text(text, strict)["hard"]
    assert "contraction" not in CW.check_text(text, flav)["hard"]


def test_long_sentence_hard_in_strict_soft_in_flavored():
    strict = WP.load("procedure")
    flav = WP.load("research")
    long = "word " * 40 + "end."
    assert "long_sentence" in CW.check_text(long, strict)["hard"]
    assert "long_sentence" not in CW.check_text(long, flav)["hard"]


def test_keep_allowlist_suppresses_a_ban_list_hit():
    # The mechanism, tested to bite: the same banned word counts without keep
    # and stops counting when the profile keeps it.
    base = WP.load("readme")
    kept = WP.load("readme")
    kept["keep"] = tuple(kept["keep"]) + ("leverage",)
    text = "We leverage the receipt."
    assert CW.check_text(text, base)["violations"].get("banned_word", 0) >= 1
    assert CW.check_text(text, kept)["violations"].get("banned_word", 0) == 0


def test_per100w_is_normalized():
    prof = WP.load("readme")
    r = CW.check_text(("seamless " * 5) + ("word " * 95), prof)
    assert r["words"] == 100
    assert r["per100w"] == r["total"]  # 100 words -> per100w equals total


def test_off_profile_reports_no_hard_violations():
    prof = WP.load("narrative")
    r = CW.check_text("We utilize a seamless; don't stop " + "—" + " ever.", prof)
    assert r["hard"] == []


def test_output_string_carries_the_does_not_prove_line():
    assert "form" in CW.DOES_NOT_PROVE.lower()
    assert "not" in CW.DOES_NOT_PROVE.lower()
