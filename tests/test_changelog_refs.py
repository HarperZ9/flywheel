"""Common Changelog's rule as a check: every entry names its receipt.

An entry that references a PR, commit, or issue creates an audit trail from
the user-facing description back to the change. That is no-receipt-no-accept
at the document layer, and only the changelog profile enforces it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import check_writing as CW  # noqa: E402
import writing_profiles as WP  # noqa: E402

REFERENCED = """## 1.2.0

- Reduced API time by caching (#123)
- Fixed the auth loop (a1b2c3d)
- New export path (https://github.com/x/y/pull/9)
"""
BARE = """## 1.2.0

- Improved performance
- Fixed some bugs
"""


def test_referenced_entries_pass_the_changelog_gate():
    r = CW.check_text(REFERENCED, WP.load("changelog"))
    assert "unreferenced_entry" not in r["violations"]
    assert r["hard"] == []


def test_bare_entries_fail_the_changelog_gate():
    r = CW.check_text(BARE, WP.load("changelog"))
    assert r["violations"].get("unreferenced_entry", 0) == 2
    assert "unreferenced_entry" in r["hard"]


def test_other_profiles_never_count_unreferenced_entries():
    for name in ("readme", "research", "procedure", "narrative"):
        r = CW.check_text(BARE, WP.load(name))
        assert "unreferenced_entry" not in r["violations"], name


def test_a_seven_char_hex_word_counts_as_a_reference_and_shorter_does_not():
    ok = CW.check_text("## 1.0\n\n- Fixed the loop (abcdef1)\n",
                       WP.load("changelog"))
    assert "unreferenced_entry" not in ok["violations"]
    short = CW.check_text("## 1.0\n\n- Fixed the loop (abcdef)\n",
                          WP.load("changelog"))
    assert short["violations"].get("unreferenced_entry", 0) == 1


def test_non_bullet_prose_in_a_changelog_is_not_an_entry():
    text = "## 1.0\n\nThis release focuses on stability.\n\n- Real entry (#1)\n"
    r = CW.check_text(text, WP.load("changelog"))
    assert "unreferenced_entry" not in r["violations"]


def test_changelog_hard_tuple_is_flavored_plus_the_reference_rule():
    rec = WP.load("changelog")
    import writing_lists as WL
    assert set(rec["hard"]) == set(WL.HARD_DEFAULTS["flavored"]) | {
        "unreferenced_entry"}


def test_backtick_wrapped_references_still_count():
    ok = CW.check_text("## 1.0\n\n- Fixed the loop (`a1b2c3d`)\n",
                       WP.load("changelog"))
    assert "unreferenced_entry" not in ok["violations"]


def test_fenced_code_bullets_are_not_entries():
    text = ("## 1.0\n\n- Real entry (#1)\n\n"
            "```yaml\n- not: an entry\n- also: code\n```\n")
    r = CW.check_text(text, WP.load("changelog"))
    assert "unreferenced_entry" not in r["violations"]


def test_a_hex_looking_english_word_is_not_a_reference():
    r = CW.check_text("## 1.0\n\n- Fixed the defaced page\n",
                      WP.load("changelog"))
    assert r["violations"].get("unreferenced_entry", 0) == 1


def test_a_real_sha_with_digits_still_counts():
    r = CW.check_text("## 1.0\n\n- Fixed the loop (deadbe3f)\n",
                      WP.load("changelog"))
    assert "unreferenced_entry" not in r["violations"]
