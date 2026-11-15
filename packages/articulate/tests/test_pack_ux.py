"""The UX microcopy pack: length limits, case, vague errors, and link text.

Each rule has a positive case, a negative case, and a control: an option that
switches it off or a gate check that shows a LOW rule reports without blocking.
"""
import pytest

from articulate import checkext, domains, profiles


def _run(text, **opts):
    prof = domains.load_profile("ux-microcopy")
    if opts:
        prof = dict(prof, options={"ux-microcopy": opts})
    return checkext.check_text(text, profile=prof)


def _cats(text, **opts):
    r = _run(text, **opts)
    return [f["category"] for f in r["high"] + r["medium"] + r["low"]]


@pytest.mark.parametrize("line,flagged", [
    ("button: Save changes", False),
    ("button: Save and continue to the next step", True),        # 7 words
    ("button: Synchronization preferences", True),                # 35 characters
    ("label: Work email", False),
    ("label: Enter the email address you use", True),
    ("error: The upload failed because the file is over 10 MB. Choose a smaller file.", False),
    ('"save_button": "Save and continue later today",', True),   # typed by its key
    ('"greeting": "Hello there friend and dear colleague",', False),  # generic text
])
def test_length_limits(line, flagged):
    assert ("ux-length" in _cats(line + "\n")) is flagged


def test_error_sentence_limit():
    long_error = "error: " + " ".join(["word"] * 30) + ". Try again.\n"
    assert "ux-length" in _cats(long_error)
    assert "ux-length" not in _cats(long_error, error_max_words=40)


def test_length_limits_are_options():
    assert "ux-length" not in _cats("button: Save and continue to the next step\n",
                                    button_max_words=8, button_max_chars=60)


def test_length_gates_under_the_strict_profile():
    assert _run("button: Save and continue to the next step\n")["gate"] == "blocked"


@pytest.mark.parametrize("line,case,flagged", [
    ("title: Account Settings", "sentence", True),
    ("title: Account settings", "sentence", False),
    ("title: Account settings", "title", True),
    ("title: Account Settings", "title", False),
    ("title: Account Settings", "off", False),
    ("title: API keys", "sentence", False),       # an acronym is not title case
])
def test_case_follows_the_option(line, case, flagged):
    assert ("ux-case" in _cats(line + "\n", case=case)) is flagged


def test_case_reports_without_blocking():
    r = _run("title: Account Settings\n")
    assert [f["category"] for f in r["low"]] == ["ux-case"] and r["gate"] == "ok"


@pytest.mark.parametrize("line,flagged", [
    ("error: Something went wrong.", True),
    ("error: Something went wrong. Try again in a minute.", False),
    ("error: Password is too short.", False),
    ("error: Upload rejected.", True),
    ("Oops, an error occurred.", True),
    ("Your changes are saved.", False),
])
def test_vague_error(line, flagged):
    assert ("ux-vague-error" in _cats(line + "\n")) is flagged


@pytest.mark.parametrize("line,flagged", [
    ("For details, click here.", True),
    ("Read the [docs](https://example.com/docs) or [here](https://example.com/x).", True),
    ('See <a href="/billing">here</a> for plans.', True),
    ("Read the [billing guide](https://example.com/billing).", False),
])
def test_link_text(line, flagged):
    assert ("ux-link-text" in _cats(line + "\n")) is flagged


def test_pack_runs_only_under_its_profile():
    r = checkext.check_text("button: Save and continue to the next step\n",
                              profile=profiles.load("flavored"))
    assert not any(f["category"].startswith("ux-") for f in r["medium"] + r["low"])


def test_button_word_limit_fires_on_its_own():
    # 5 short words, 14 characters: only the word limit can flag it.
    assert "ux-length" in _cats("button: Go to my list\n")
    assert "ux-length" not in _cats("button: Go to my list\n", button_max_words=5)
