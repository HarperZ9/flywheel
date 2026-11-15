"""The meaning guard: surface invariants a rewrite must keep.

Each case pairs a faithful rewrite, which must read `preserved`, with an
unfaithful one, which must report the named status for that kind. The faithful
side is the false-positive control; the unfaithful side fails if the kind's
extractor is removed. One test pins the documented blind spot, so the
does-not-prove statement stays honest.
"""
import pytest

from articulate import invariants, meaning, quantities

CASES = [
    # kind, original, faithful rewrite, unfaithful rewrite, expected status
    ("number", "Retry 3 times within 10 ms.", "Retry three times within 10ms.",
     "Retry 3 times within 20 ms.", "changed"),
    ("number", "Load stays under 50% of capacity.",
     "Load stays under 50 percent of capacity.",
     "Load stays under 60% of capacity.", "changed"),
    ("number", "It shipped on May 5, 2026.", "It shipped on 2026-05-05.",
     "It shipped on May 6, 2026.", "changed"),
    ("number", "Install v1.2.3 first.", "Install 1.2.3 first.",
     "Install v1.2.4 first.", "changed"),
    ("number", "The pool holds 1,000 rows.", "The pool holds 1000 rows.",
     "The pool holds rows.", "dropped"),
    ("negation", "The cache is not shared.", "The cache isn't shared.",
     "The cache is shared.", "dropped"),
    ("negation", "Run the job.", "Run the job now.", "Never run the job.", "added"),
    ("modal", "Clients MUST retry.", "Clients SHALL retry.",
     "Clients SHOULD retry.", "changed"),
    ("modal", "You must sign in.", "You have to sign in.", "You can sign in.",
     "changed"),
    ("modal", "Clients MUST retry.", "Clients MUST retry at once.",
     "Clients must retry.", "changed"),
    ("scope", "Only admins can delete it.", "Only admins may delete it.",
     "Admins can delete it.", "dropped"),
    ("scope", "Users must reset all passwords.", "Users must reset every password.",
     "Users must reset some passwords.", "changed"),
    ("entity", "We deploy the service on Kubernetes today.",
     "Kubernetes runs the service today.",
     "We deploy the service on Nomad today.", "changed"),
    ("url", "Read https://example.com/a first.", "First, read https://example.com/a.",
     "Read https://example.com/b first.", "changed"),
    ("url", "Mail ops@example.com today.", "Today, mail ops@example.com.",
     "Mail the ops team today.", "dropped"),
    ("url", "See https://en.wikipedia.org/wiki/Mercury_(planet) now.",
     "Now see https://en.wikipedia.org/wiki/Mercury_(planet).",
     "See https://en.wikipedia.org/wiki/Mercury_(planet now.", "changed"),
    ("code", "Set `retries = 3` in the file.", "In the file, set `retries = 3`.",
     "Set `retries = 5` in the file.", "changed"),
    ("code", "Run this:\n\n```\nmake test\n```\n", "Run the tests:\n\n```\nmake test\n```\n",
     "Run this:\n\n```\nmake check\n```\n", "changed"),
    ("math", "The bound $x^2 \\le y$ holds.", "The bound $x^2 \\le y$ still holds.",
     "The bound $x^3 \\le y$ holds.", "changed"),
    ("citation", "This holds [1].", "This result holds [1].", "This holds.", "dropped"),
    ("citation", "As shown (Smith, 2020).", "As shown before (Smith, 2020).",
     "As shown (Smith, 2021).", "changed"),
    ("citation", "See arXiv:2301.01234 for details.", "For details, see arXiv:2301.01234.",
     "See the preprint for details.", "dropped"),
    ("citation", "Cited as doi:10.1000/xyz123 here.", "Here it is cited as doi:10.1000/xyz123.",
     "Cited here.", "dropped"),
    ("quote", 'She wrote "ship it Friday" in the log.',
     'In the log she wrote "ship it Friday".',
     'She wrote "ship it Monday" in the log.', "changed"),
]


def _statuses(report, kind):
    return {r["status"] for r in report["items"] if r["kind"] == kind}


@pytest.mark.parametrize("kind,original,faithful,unfaithful,status", CASES)
def test_faithful_rewrite_is_preserved(kind, original, faithful, unfaithful, status):
    report = meaning.compare(original, faithful)
    assert report["verdict"] == "preserved", meaning.format_report(report)


@pytest.mark.parametrize("kind,original,faithful,unfaithful,status", CASES)
def test_unfaithful_rewrite_is_caught(kind, original, faithful, unfaithful, status):
    report = meaning.compare(original, unfaithful)
    assert report["verdict"] == "changed"
    assert status in _statuses(report, kind), meaning.format_report(report)


def test_freeze_term_is_an_invariant():
    original = "The receipt reads Match here."
    kept = meaning.compare(original, "Here the receipt reads Match.", freeze=("Match",))
    lost = meaning.compare(original, "Here the receipt reads a match.", freeze=("Match",))
    assert kept["verdict"] == "preserved"
    assert "dropped" in _statuses(lost, "freeze")


def test_freeze_term_keeps_its_key_across_normalization_forms():
    nfc, nfd = "Ask Zo\u00eb about it.", "Ask Zoe\u0308 about it."
    assert meaning.compare(nfd, nfc, freeze=("Zo\u00eb",))["verdict"] == "preserved"
    lost = meaning.compare(nfd, "Ask Zoe about it.", freeze=("Zo\u00eb",))
    assert "dropped" in _statuses(lost, "freeze")


def test_identical_text_is_preserved_with_every_item_kept():
    text = ("Clients MUST NOT retry more than 3 times (Smith et al., 2020) unless "
            "`force=1` is set; see https://example.com.")
    report = meaning.compare(text, text)
    assert report["verdict"] == "preserved"
    assert report["counts"]["kept"] == len(report["items"]) > 5


def test_locations_are_line_and_column():
    report = meaning.compare("Intro.\nRetry 3 times.\n", "Intro.\nRetry 4 times.\n")
    row = next(r for r in report["items"] if r["kind"] == "number")
    assert (row["before"]["line"], row["before"]["col"]) == (2, 7)
    assert row["before"]["text"] == "3" and row["after"]["text"] == "4"


def test_container_claims_its_inner_tokens_once():
    items = invariants.extract("then visit https://example.com/v2/items?id=7 now.")
    assert [i["kind"] for i in items] == ["url"]


def test_report_states_what_the_checks_cover():
    report = meaning.compare("a", "b")
    assert "surface markers" in report["scope"]
    text = meaning.format_report(report)
    assert "Read the rewrite to confirm the meaning." in text
    assert "does not prove" not in text


def test_moved_negation_is_a_documented_blind_spot():
    """The count of negations is kept, so the guard reads this as preserved even
    though the meaning flipped twice. This is the limit the report states."""
    report = meaning.compare("The cache is not shared. The log is local.",
                             "The cache is shared. The log is not local.")
    assert report["verdict"] == "preserved"


@pytest.mark.parametrize("text,key", [
    ("three days", "3d"), ("3d", "3d"), ("twenty-five percent", "25%"),
    ("1.5 million", "1500000"), ("10k", "10000"), ("-4", "-4"),
    ("5 May 2026", "date:2026-05-05"), ("10:30 AM", "time:10:30am"),
])
def test_quantity_normalization(text, key):
    assert [k for _s, _e, k in quantities.find(text)] == [key]


def test_one_and_identifiers_are_not_numbers():
    assert quantities.find("the one that uses sha256 and abc123") == []


def test_tex_backtick_quotes_are_prose_not_code():
    original = "Use ``quick'' and ``slow'' modes."
    rewrite = "Use ``quick'' or ``slow'' modes."
    assert meaning.compare(original, rewrite, tex=True)["verdict"] == "preserved"
    assert "changed" in _statuses(meaning.compare(original, rewrite), "code")


def test_quotes_off_reads_quoted_words_as_prose():
    original = 'She wrote "ship it Friday" in the log.'
    report = meaning.compare(original, 'She wrote "ship it Monday" in the log.', quotes=False)
    assert "quote" not in report["by_kind"]
    assert "changed" in _statuses(report, "number") | _statuses(report, "entity")


def test_blocking_honors_allowed_kinds():
    report = meaning.compare("Retry 3 times.", "Retry 4 times.")
    assert meaning.blocking(report) and not meaning.blocking(report, {"number"})


@pytest.mark.parametrize("marker", ["`", "~"])
def test_shorter_fence_inside_code_does_not_end_the_full_span(marker):
    block = f"{marker * 4}\nalpha\n{marker * 3}\naccess=false\n{marker * 4}"
    prefix = "run this:\n\n"
    text = prefix + block + "\n\nready."
    codes = [item for item in invariants.extract(text) if item["kind"] == "code"]
    assert [(item["start"], item["end"], item["text"]) for item in codes] == [
        (len(prefix), len(prefix) + len(block), block)]


@pytest.mark.parametrize("marker", ["`", "~"])
def test_edit_after_shorter_internal_fence_is_a_code_change(marker):
    original = f"{marker * 4}\nalpha\n{marker * 3}\naccess=false\n{marker * 4}"
    rewrite = original.replace("access=false", "access=true")
    report = meaning.compare(original, rewrite)
    assert report["verdict"] == "changed", meaning.format_report(report)
    assert "changed" in _statuses(report, "code")


@pytest.mark.parametrize("marker", ["`", "~"])
@pytest.mark.parametrize("closing_length", [4, 5])
def test_equal_or_longer_fence_closes_before_following_prose(marker, closing_length):
    block = f"{marker * 4}\naccess=false\n{marker * closing_length}"
    original = block + "\n\nready."
    rewrite = block + "\n\nwaiting."
    assert invariants.fenced_blocks(original) == [(0, len(block))]
    report = meaning.compare(original, rewrite)
    assert report["verdict"] == "preserved", meaning.format_report(report)
