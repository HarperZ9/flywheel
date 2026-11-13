"""Falsifiers for the scrubber that runs before a provider message is kept.

Load-bearing: (1) the shared SECRET_PATTERNS set misses every modern vendor key
shape, and this is asserted against the real scanner rather than described in a
comment, so the day that gap closes the test says so; (2) a key gets a digest
and a human password does not, because a 48-bit digest of a wordlist password
is a lookup; (3) truncation happens after scrubbing, so a secret near the end of
a long body is removed rather than half-printed; (4) a redacted marker is not
itself re-matched by a later, looser rule.
"""
from harness import model_redaction as rd
from harness.infra import credential_scanner as cs

# Fake credentials, assembled at import time. No line of this file holds a
# complete key-shaped literal, so a secret scanner reading the source finds
# nothing, while every test still scrubs the same value it always did.
_ALNUM = "abcdefghijklmnopqrstuvwxyz"
_HEX = "0123456789abcdef"
PROJECT_KEY = "-".join(("sk", "proj", "T3BlbkFJ" + _HEX[10:] + _HEX[:10] + "ABCDEFGH"))
ANT_KEY = "-".join(("sk", "ant", "api03", "VeryLongSecretValueHere1234"))
OR_KEY = "-".join(("sk", "or", "v1", _HEX * 2))
GOOGLE_KEY = "AI" + "za" + "SyD-" + _ALNUM + "012"
LEGACY_KEY = "sk" + "-" + _ALNUM + "0123"
PEM_HEADER = "-----BEGIN " + "RSA PRIVATE" + " KEY-----"


# --- the gap this module exists to close ------------------------------------

def test_the_shared_scanner_misses_every_modern_vendor_key_shape():
    """Not a claim about the scanner quality. Its openai rule is sk- plus an
    alphanumeric run, and every current key puts a dash four characters in, so
    the run ends before the length floor is reached. Pinned here because this
    module reason to exist disappears the day it stops being true."""
    for key in (PROJECT_KEY, ANT_KEY, OR_KEY, GOOGLE_KEY):
        assert cs.scan_text(key, "probe") == []


def test_the_scrubber_catches_what_the_shared_scanner_missed():
    for key, kind in ((PROJECT_KEY, "openai_project_key"),
                      (ANT_KEY, "anthropic_api_key"),
                      (OR_KEY, "openrouter_api_key"),
                      (GOOGLE_KEY, "google_api_key")):
        reading = rd.scrub("Incorrect API key provided: " + key)
        assert key not in reading["text"]
        assert reading["kinds"] == [kind]
        assert reading["redacted"] is True


def test_a_legacy_key_the_shared_scanner_does_catch_is_still_caught_here():
    """The two sets overlap and the overlap must not produce two markers or a
    marker nested inside another."""
    assert cs.scan_text(LEGACY_KEY, "probe") != []
    reading = rd.scrub("key " + LEGACY_KEY)
    assert reading["kinds"] == ["openai_api_key"]
    assert reading["text"].count("[redacted:") == 1


def test_a_specific_shape_names_the_match_before_the_catch_all_does():
    """vendor_prefixed_key would match an anthropic key too. Ordering is what
    makes the record say which vendor credential leaked, and a record that says
    only that some key leaked cannot be used to rotate the right one."""
    assert rd.scrub(ANT_KEY)["kinds"] == ["anthropic_api_key"]
    other = rd.scrub("-".join(("sk", "cohere", "0123456789" + _ALNUM[:10])))
    assert other["kinds"] == ["vendor_prefixed_key"]


# --- what gets a digest and what does not ------------------------------------

def test_the_same_key_in_two_records_carries_the_same_fingerprint():
    """This is the whole point of digesting: two fault records taken hours
    apart can be shown to name one leaked credential without either of them
    holding it."""
    first = rd.scrub("401 from " + ANT_KEY)["text"]
    second = rd.scrub("still 401 for " + ANT_KEY)["text"]
    digest = first.split(":")[-1].rstrip("]")
    assert digest in second
    assert len(digest) == 12


def test_the_fingerprint_agrees_with_the_credential_scanner_own():
    """Two modules that disagree about a key identity are worse than one
    module, because a search across both returns half the occurrences."""
    marker = rd.scrub(ANT_KEY)["text"]
    assert cs._fingerprint(ANT_KEY) in marker


def test_a_human_password_is_removed_and_never_digested():
    """Twelve hex characters is forty-eight bits. Against a key drawn from a
    vendor generator that is not invertible. Against a password from a wordlist
    it is a lookup, so publishing the digest publishes the password."""
    reading = rd.scrub("password: hunter2hunter2")
    assert reading["kinds"] == ["generic_password"]
    assert reading["text"] == "[redacted:generic_password]"


def test_a_private_key_header_is_not_digested_because_it_is_a_constant():
    """The match is the BEGIN line, byte-identical in every key ever issued. A
    digest of it would be the same in every record and would read as evidence
    that two records name one key."""
    reading = rd.scrub(PEM_HEADER)
    assert reading["kinds"] == ["private_key"]
    assert reading["text"] == "[redacted:private_key]"


def test_every_fingerprinted_kind_is_one_of_the_patterns_this_module_knows():
    known = {name for name, _ in rd.BOUNDARY_PATTERNS}
    known |= {name for name, _ in cs.SECRET_PATTERNS}
    assert rd.FINGERPRINTED <= known


# --- a marker is not a secret -----------------------------------------------

def test_a_redacted_marker_is_not_re_matched_by_a_looser_later_rule():
    """The generic rules run after the specific ones and look for a key-ish
    word followed by a run of characters. A marker starts with a bracket, which
    is outside every value class, so it cannot be swallowed a second time."""
    reading = rd.scrub("api_key=" + ANT_KEY)
    assert reading["kinds"] == ["anthropic_api_key"]
    assert reading["text"] == (
        "api_key=[redacted:anthropic_api_key:" + cs._fingerprint(ANT_KEY) + "]")


def test_a_bearer_header_loses_the_token_and_keeps_the_word():
    reading = rd.scrub("authorization: Bearer " + ANT_KEY)
    assert ANT_KEY not in reading["text"]
    assert "Bearer" in reading["text"]


def test_scrubbing_twice_changes_nothing_the_second_time():
    once = rd.scrub("key " + PROJECT_KEY)["text"]
    twice = rd.scrub(once)
    assert twice["text"] == once
    assert twice["kinds"] == []


# --- bounds ------------------------------------------------------------------

def test_a_secret_past_the_limit_is_removed_before_the_cut_is_made():
    """The order that matters. Cutting first leaves the key untouched in the
    part that was kept, or prints half of it at the boundary, and half a key is
    still the half an attacker needs to confirm a guess."""
    body = ("x" * 400) + " " + ANT_KEY
    reading = rd.scrub(body, limit=64)
    assert ANT_KEY not in reading["text"]
    assert reading["kinds"] == ["anthropic_api_key"]
    assert reading["truncated"] is True
    assert reading["text"].endswith(rd.TRUNCATED)
    assert reading["original_chars"] == len(body)


def test_a_short_body_is_not_marked_truncated():
    reading = rd.scrub("no secrets here")
    assert reading == {"text": "no secrets here", "redacted": False,
                       "kinds": [], "truncated": False, "original_chars": 15}


def test_something_that_was_never_text_reports_no_length_rather_than_zero():
    """An honest null. Zero characters is a measurement of an empty string, and
    a caller that treats an absent body as an empty one has lost the difference
    between a provider that said nothing and a provider never asked."""
    for junk in (None, 7, {"error": "x"}, ["x"], b"bytes"):
        reading = rd.scrub(junk)
        assert reading["original_chars"] is None
        assert reading["text"] == ""
        assert reading["kinds"] == []


def test_a_negative_or_nonsense_limit_falls_back_rather_than_emptying_the_text():
    for bad in (-1, "64", None, True):
        reading = rd.scrub("a short message", limit=bad)
        assert reading["text"] == "a short message"


# --- the nested walk ---------------------------------------------------------

def test_a_nested_upstream_body_is_scrubbed_at_every_level():
    """What a routing proxy hands back under error.metadata.raw is an arbitrary
    object from a third party, and the credential in it is as live as one in a
    top-level message."""
    reading = rd.scrub_value(
        {"error": {"message": "bad key " + ANT_KEY,
                   "metadata": {"raw": {"detail": ["nested " + GOOGLE_KEY]}}}})
    flat = repr(reading["value"])
    assert ANT_KEY not in flat
    assert GOOGLE_KEY not in flat
    assert sorted(reading["kinds"]) == ["anthropic_api_key", "google_api_key"]
    assert reading["bounded"] is False


def test_a_structure_deeper_than_the_bound_says_so_rather_than_recursing():
    node = "leaf"
    for _ in range(20):
        node = {"next": node}
    reading = rd.scrub_value(node, depth=3)
    assert reading["bounded"] is True
    assert "depth_exceeded" in repr(reading["value"])


def test_a_long_list_is_cut_and_the_cut_is_reported():
    reading = rd.scrub_value(list(range(100)), items=4)
    assert reading["value"] == [0, 1, 2, 3]
    assert reading["bounded"] is True


def test_a_value_of_a_type_the_walker_does_not_know_is_kept_as_its_repr():
    """Dropping it would lose evidence. Keeping it raw would put an object of
    unknown shape into a durable record, so it becomes text and the text is
    scrubbed like any other."""

    class Odd:
        def __repr__(self):
            return "<Odd " + ANT_KEY + ">"

    reading = rd.scrub_value({"thing": Odd()})
    assert ANT_KEY not in repr(reading["value"])
    assert reading["kinds"] == ["anthropic_api_key"]


def test_scalars_survive_the_walk_with_their_types_intact():
    reading = rd.scrub_value({"a": 1, "b": 1.5, "c": True, "d": None})
    assert reading["value"] == {"a": 1, "b": 1.5, "c": True, "d": None}
    assert reading["kinds"] == []
    assert reading["bounded"] is False
