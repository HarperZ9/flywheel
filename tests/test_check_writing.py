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
    r = CW.check_text("This is a clause - and another.".replace("-", "\u2014"), prof)
    assert r["em_dash"] == 1
    assert "em_dash" in r["hard"]


def test_narrative_profile_never_flags_em_dash():
    prof = WP.load("narrative")
    r = CW.check_text("A long dash lives here" + "\u2014" + "and stays.", prof)
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
    flav["max_sentence_words"] = 25
    long = "word " * 40 + "end."
    r_strict = CW.check_text(long, strict)
    r_flav = CW.check_text(long, flav)
    assert "long_sentence" in r_strict["hard"]
    # Counted in flavored, so the soft path is real, yet not a hard failure.
    assert r_flav["violations"].get("long_sentence", 0) >= 1
    assert "long_sentence" not in r_flav["hard"]


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
    r = CW.check_text("We utilize a seamless; don't stop " + "\u2014" + " ever.", prof)
    assert r["hard"] == []


def test_output_string_carries_the_does_not_prove_line():
    assert "form" in CW.DOES_NOT_PROVE.lower()
    assert "not" in CW.DOES_NOT_PROVE.lower()


def test_multi_word_and_phrasal_and_hedge_phrases_are_counted():
    prof = WP.load("research")
    r = CW.check_text(
        "Prior to launch, we dive into logs. It is worth noting the cache.",
        prof)
    assert r["violations"].get("banned_word", 0) >= 1
    assert r["violations"].get("phrasal_verb", 0) >= 1
    assert r["violations"].get("modal_hedge", 0) >= 1


def test_phrase_split_across_a_line_break_is_still_caught():
    prof = WP.load("research")
    r = CW.check_text("We act prior\nto launch.", prof)
    assert r["violations"].get("banned_word", 0) >= 1


def test_possessive_s_is_not_a_contraction():
    prof = WP.load("procedure")
    clean = CW.check_text("The system's output holds.", prof)
    assert "contraction" not in clean["violations"]
    real = CW.check_text("It's ready.", prof)
    assert real["violations"].get("contraction", 0) == 1


import subprocess  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _run(*args, stdin=None):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_writing.py"), *args],
        capture_output=True, text=True, cwd=ROOT, input=stdin)


def test_delta_is_new_minus_old():
    prof = WP.load("readme")
    d = CW.delta("seamless " * 5 + "word " * 95, "word " * 100, prof)
    assert d["old"] > d["new"]
    assert round(d["delta"], 2) == round(d["new"] - d["old"], 2)


def test_gate_fails_on_a_hard_violation(tmp_path):
    f = tmp_path / "bad.md"
    f.write_text("This is a seamless powerful tool.\n", encoding="utf-8")
    r = _run("--profile", "readme", "--gate", str(f))
    assert r.returncode == 1, r.stdout + r.stderr


def test_gate_passes_clean_text(tmp_path):
    f = tmp_path / "ok.md"
    f.write_text("The parser reads the file. It returns a record.\n",
                 encoding="utf-8")
    r = _run("--profile", "readme", "--gate", str(f))
    assert r.returncode == 0, r.stdout + r.stderr


def test_report_mode_never_fails_even_on_slop(tmp_path):
    f = tmp_path / "bad.md"
    f.write_text("This is a seamless powerful tool.\n", encoding="utf-8")
    r = _run("--profile", "readme", str(f))
    assert r.returncode == 0


def test_json_output_carries_score_and_disclaimer(tmp_path):
    import json
    f = tmp_path / "x.md"
    f.write_text("word " * 20 + "seamless.\n", encoding="utf-8")
    r = _run("--profile", "readme", "--json", str(f))
    doc = json.loads(r.stdout)
    assert doc["files"][0]["per100w"] >= 0
    assert "form" in doc["does_not_prove"].lower()


def test_profile_is_inferred_from_path_when_not_given(tmp_path):
    d = tmp_path / "essays"
    d.mkdir()
    f = d / "piece.md"
    f.write_text("A dash lives here " + "\\u2014" + " and stays.\\n", encoding="utf-8")
    # narrative profile -> em-dash not hard -> gate passes
    assert _run("--gate", str(f)).returncode == 0
