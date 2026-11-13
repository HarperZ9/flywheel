"""Falsifiers for the two clocks a provider answers a rate limit on.

Hermetic: literal header dicts, no clock and no network. Load-bearing: (1) a Go
duration read by a bare integer parse turns 6m0s into 6, so a client waits six
seconds for a limit that clears in three hundred and sixty; (2) a relative row
and an absolute row do not share a key, so a caller cannot silently read one as
the other; (3) a value that does not match its documented format refuses rather
than being coerced, because a coerced deadline is a wrong wait that looks like
a right one; (4) a header present but unreadable is reported as unread rather
than as absent, so a spelling change surfaces instead of disappearing.
"""
from harness import model_deadlines as md
from harness.model_dialects import (ANTHROPIC, GEMINI, OLLAMA, OPENAI,
                                    OPENAI_RESPONSES)

RESET = "2026-09-11T22:00:00Z"


def _row(rows, header):
    return next(r for r in rows if r["header"] == header)


# --- the misread this module exists to prevent -------------------------------

def test_a_go_duration_of_six_minutes_reads_as_three_hundred_and_sixty():
    """The whole reason the reset family gets its own parser. Read as a bare
    integer this is 6, and a client that waits 6 seconds hits the same wall on
    every attempt until the real window closes on its own."""
    assert md.go_duration("6m0s") == 360.0
    assert md.go_duration("1s") == 1.0
    assert md.go_duration("1h30m") == 5400.0
    assert md.go_duration("88ms") == 0.088


def test_a_unitless_value_in_a_reset_slot_refuses_rather_than_reading_seconds():
    """A bare number is not a Go duration. Accepting it would mean the parser
    disagrees with itself about what the header contains, and the disagreement
    is invisible because both readings produce a number."""
    for junk in ("6", "6.0", "", "soon", None, 6, True):
        assert md.go_duration(junk) is None


def test_a_negative_go_duration_keeps_its_sign():
    assert md.go_duration("-1s") == -1.0


# --- the seconds parser ------------------------------------------------------

def test_retry_after_reads_an_integer_count_of_seconds():
    assert md.seconds("56") == 56.0
    assert md.seconds(12) == 12.0
    assert md.seconds("1.5") == 1.5


def test_an_http_date_in_retry_after_refuses_rather_than_being_coerced():
    """RFC 7231 allows a date here and both vendors in this table document a
    count of seconds. A date coerced through a numeric parse either raises or,
    worse, yields a year, and a wait of fifty years is indistinguishable from a
    hang."""
    assert md.seconds("Wed, 21 Oct 2026 07:28:00 GMT") is None


def test_a_negative_or_non_numeric_wait_refuses():
    for junk in (-1, "-1", "soon", None, True, False, [], {}):
        assert md.seconds(junk) is None


# --- the instant parser ------------------------------------------------------

def test_an_rfc3339_instant_reads_as_an_epoch():
    assert md.rfc3339(RESET) == 1789164000.0
    assert md.rfc3339("2026-09-11T22:00:00+00:00") == 1789164000.0


def test_an_offsetless_string_refuses_rather_than_defaulting_to_utc():
    """RFC 3339 requires an offset. Defaulting a naive string to UTC moves the
    instant by the reader own timezone, so the same header read on two machines
    names two different moments and neither reader can tell."""
    assert md.rfc3339("2026-09-11T22:00:00") is None
    for junk in ("", "tomorrow", None, 17, []):
        assert md.rfc3339(junk) is None


# --- the two bases do not share a key ----------------------------------------

def test_an_anthropic_response_separates_the_wait_from_the_instant():
    rows = md.read({"retry-after": "12",
                    "anthropic-ratelimit-tokens-reset": RESET},
                   dialect=ANTHROPIC)
    wait = _row(rows, "retry-after")
    assert wait["basis"] == md.RELATIVE_SECONDS
    assert wait["seconds"] == 12.0
    assert "epoch" not in wait
    instant = _row(rows, "anthropic-ratelimit-tokens-reset")
    assert instant["basis"] == md.ABSOLUTE_INSTANT
    assert instant["epoch"] == 1789164000.0
    assert "seconds" not in instant


def test_the_openai_reset_family_is_relative_and_the_anthropic_one_is_not():
    """Same word in both header names, opposite meaning. This is the pair a
    single table keyed on the word reset would collapse."""
    openai = _row(md.read({"x-ratelimit-reset-tokens": "6m0s"}, dialect=OPENAI),
                  "x-ratelimit-reset-tokens")
    assert openai["basis"] == md.RELATIVE_SECONDS
    assert openai["seconds"] == 360.0
    anthropic = _row(
        md.read({"anthropic-ratelimit-requests-reset": RESET}, dialect=ANTHROPIC),
        "anthropic-ratelimit-requests-reset")
    assert anthropic["basis"] == md.ABSOLUTE_INSTANT
    assert "seconds" not in anthropic


def test_every_row_keeps_the_value_it_was_read_from():
    rows = md.read({"Retry-After": "56"}, dialect=OPENAI)
    assert rows[0]["verbatim"] == "56"
    assert rows[0]["read"] is True


# --- unreadable is not absent ------------------------------------------------

def test_a_header_that_does_not_parse_is_reported_unread_with_its_value():
    """Dropping it would report a response that carried a deadline as one that
    carried none, and the vendor changing a format would look like the vendor
    removing a header."""
    rows = md.read({"x-ratelimit-reset-requests": "60"}, dialect=OPENAI)
    assert rows[0]["read"] is False
    assert rows[0]["verbatim"] == "60"
    assert "seconds" not in rows[0]


def test_header_names_are_matched_without_regard_to_case():
    rows = md.read({"RETRY-AFTER": "3"}, dialect=OPENAI)
    assert rows[0]["seconds"] == 3.0


def test_a_non_string_header_name_does_not_break_the_read():
    rows = md.read({7: "x", "retry-after": "3"}, dialect=OPENAI)
    assert rows[0]["seconds"] == 3.0


# --- dialects that assert nothing --------------------------------------------

def test_the_two_dialects_with_no_documented_timing_header_read_nothing():
    """An honest null. Gemini documents backoff inside error.details and this
    table has not read a spelling for it, so it claims no header rather than
    guessing one. ollama defines none on either envelope."""
    for dialect in (GEMINI, OLLAMA):
        assert md.DEADLINE_HEADERS[dialect] == ()
        assert md.read({"retry-after": "5"}, dialect=dialect) == []


def test_the_responses_endpoint_shares_the_chat_endpoint_table():
    assert (md.DEADLINE_HEADERS[OPENAI_RESPONSES]
            is md.DEADLINE_HEADERS[OPENAI])


def test_an_unmapped_dialect_reads_nothing_rather_than_raising():
    assert md.read({"retry-after": "5"}, dialect="cohere") == []


def test_headers_we_never_saw_read_as_no_rows():
    for junk in (None, [], "retry-after: 5", 7):
        assert md.read(junk, dialect=OPENAI) == []


# --- choosing between rows ---------------------------------------------------

def test_the_soonest_wait_is_the_shortest_relative_row():
    rows = md.read({"retry-after": "56", "x-ratelimit-reset-requests": "1s",
                    "x-ratelimit-reset-tokens": "6m0s"}, dialect=OPENAI)
    assert md.soonest(rows)["header"] == "x-ratelimit-reset-requests"


def test_an_absolute_row_is_skipped_rather_than_converted():
    """Converting it needs a clock. This module does not read one, so a
    response carrying only absolute rows answers None and the caller that has
    the current time does the subtraction where the reading is used."""
    rows = md.read({"anthropic-ratelimit-tokens-reset": RESET},
                   dialect=ANTHROPIC)
    assert rows and md.soonest(rows) is None


def test_soonest_on_nothing_answers_none():
    for junk in (None, [], "rows", [{"header": "x"}]):
        assert md.soonest(junk) is None
