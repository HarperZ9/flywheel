"""The code review pack: condescension markers, requests without a reason, and
absolute language about a person. The profile gates at the flavored level, so
these rules report; a control shows a banned device still blocks.
"""
import pytest

from articulate import checkext, domains, profiles


def _run(text):
    return checkext.check_text(text, profile=domains.load_profile("code-review"))


def _tiers(text, cat):
    r = _run(text)
    return sorted(f["tier"] for f in r["high"] + r["medium"] + r["low"] if f["category"] == cat)


@pytest.mark.parametrize("text,tiers", [
    ("Just use a dict here, since lookups are faster.\n", ["LOW"]),
    ("Use a dict here, since lookups are faster.\n", []),
    ("Why didn't you run the tests before pushing?\n", ["MEDIUM"]),
    ("Did the tests run before the push?\n", []),
])
def test_condescension(text, tiers):
    assert _tiers(text, "review-condescension") == tiers


@pytest.mark.parametrize("text,flagged", [
    ("Please rename this variable.\n", True),
    ("Please rename this variable, since it holds a count.\n", False),
    ("Please rename this. It hides that the value is mutated.\n", False),
    ("Please rename this.\n\nThis breaks the build on Windows.\n", True),
    ("Can you move this into the helper?\n", True),
    ("The helper already covers this case.\n", False),
])
def test_request_needs_a_reason_in_the_same_comment(text, flagged):
    assert bool(_tiers(text, "review-no-reason")) is flagged


@pytest.mark.parametrize("text,flagged", [
    ("You always forget the null check.\n", True),
    ("Your code is wrong here.\n", True),
    ("This path skips the null check.\n", False),
])
def test_absolute_language_about_a_person(text, flagged):
    assert bool(_tiers(text, "review-absolute")) is flagged


def test_review_rules_report_but_devices_still_gate():
    assert _run("Why didn't you run the tests? You always skip them.\n")["gate"] == "ok"
    assert _run("This is not a bug, but a feature of the parser.\n")["gate"] == "blocked"
