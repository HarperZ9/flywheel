"""The hedging field toggles a real check: filler-free is not enough in a
procedure; uncertainty WORDS are banned there too, while calibrated registers
keep them, because calibrated uncertainty is precision, not slop.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import check_writing as CW  # noqa: E402
import writing_lists as WL  # noqa: E402
import writing_profiles as WP  # noqa: E402

HEDGED = "This might work. Perhaps restart the unit. It could possibly help."


def test_banned_hedging_counts_hedge_words():
    r = CW.check_text(HEDGED, WP.load("procedure"))
    assert r["violations"].get("hedge_word", 0) >= 3
    assert "hedge_word" in r["hard"]


def test_calibrated_hedging_keeps_uncertainty_words():
    for name in ("research", "chat", "model-card"):
        r = CW.check_text(HEDGED, WP.load(name))
        assert "hedge_word" not in r["violations"], name


def test_verdict_vocabulary_is_never_a_hedge():
    text = "The verdict is UNDECIDED. The claim is UNVERIFIABLE."
    r = CW.check_text(text, WP.load("procedure"))
    assert "hedge_word" not in r["violations"]


def test_every_strict_profile_bans_hedging_so_the_hard_default_is_coherent():
    for name, rec in WP.PROFILES.items():
        if rec["slop"] == "strict":
            assert rec["hedging"] == "banned", name
    assert "hedge_word" in WL.HARD_DEFAULTS["strict"]
    assert "hedge_word" not in WL.HARD_DEFAULTS["flavored"]


def test_hedge_words_are_gate_capable_not_report_only():
    assert "hedge_word" in WL.KNOWN_CATEGORIES
    assert "hedge_word" not in WL.REPORT_ONLY_CATEGORIES


def test_hedge_word_boundaries_do_not_match_inside_words():
    r = CW.check_text("The mightiest turbine is here.", WP.load("procedure"))
    assert "hedge_word" not in r["violations"]


def test_flavored_profiles_with_banned_hedging_count_but_never_gate():
    # changelog and normative-spec ban hedging (they are normative surfaces)
    # while carrying flavored hard tuples, so hedge words inform their score
    # and never fail their gate. Pinned so the behavior is a contract, not an
    # accident of two tuples.
    text = "Perhaps this might help."
    for name in ("changelog", "normative-spec"):
        r = CW.check_text(text, WP.load(name))
        assert r["violations"].get("hedge_word", 0) >= 2, name
        assert "hedge_word" not in r["hard"], name
