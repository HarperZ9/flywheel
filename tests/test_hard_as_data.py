"""The block-versus-report split lives in profile data, and it fails loudly.

Spec 4.4: "The block-versus-report split is itself in the profile data." Until
now HARD_BY_SLOP was engine code; a profile could not narrow or widen its gate.
Now every profile carries a hard tuple, the engine reads it, and the two ways
the data could lie (an unknown category, a report-only category smuggled into
hard) raise instead of silently gating wrong.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import check_writing as CW  # noqa: E402
import writing_lists as WL  # noqa: E402
import writing_profiles as WP  # noqa: E402


def test_every_profile_carries_a_hard_tuple_matching_its_slop_default():
    for name, rec in WP.PROFILES.items():
        assert "hard" in rec, name
        if name != "changelog":
            assert tuple(sorted(rec["hard"])) == tuple(
                sorted(WL.HARD_DEFAULTS[rec["slop"]])), name


def test_the_engine_reads_hard_from_the_profile_not_the_slop_level():
    prof = WP.load("readme")
    prof["hard"] = ("em_dash",)          # narrow the gate to em-dash only
    r = CW.check_text("A seamless tool.", prof)
    assert r["violations"].get("marketing_adjective", 0) >= 1
    assert r["hard"] == []               # marketing no longer hard here


def test_an_unknown_hard_category_raises():
    prof = WP.load("readme")
    prof["hard"] = ("no_such_category",)
    with pytest.raises(WP.ProfileError):
        CW.check_text("Any text.", prof)


def test_a_report_only_category_in_hard_raises():
    prof = WP.load("readme")
    prof["hard"] = ("passive_voice",)
    with pytest.raises(WP.ProfileError):
        CW.check_text("Any text.", prof)


def test_load_validates_hard_at_load_time_too():
    WP.PROFILES["_broken"] = dict(WP.PROFILES["readme"], hard=("be_verb",))
    try:
        with pytest.raises(WP.ProfileError):
            WP.load("_broken")
    finally:
        del WP.PROFILES["_broken"]


def test_hard_by_slop_is_an_alias_of_the_data():
    for level, cats in CW.HARD_BY_SLOP.items():
        assert cats == frozenset(WL.HARD_DEFAULTS[level])


def test_known_categories_cover_everything_the_engine_emits():
    text = ("Don't use a seamless; tool. We utilize it prior to launch. "
            "It is worth noting the file is read while running checks. "
            "We perform analysis of the " + "\u2014" + " utilization of it. "
            + " ".join(f"Sentence {i} here." for i in range(8)))
    prof = WP.load("research")
    prof["max_sentence_words"] = 5
    r = CW.check_text(text, prof)
    assert set(r["violations"]) <= WL.KNOWN_CATEGORIES


def test_moved_patterns_are_the_same_objects():
    assert CW._PASSIVE is WL.PASSIVE
    assert CW._ING_MAIN is WL.ING_MAIN
    assert CW._NOMINAL is WL.NOMINAL
