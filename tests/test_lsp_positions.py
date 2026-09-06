"""What an LSP `character` counts, checked where Python and LSP disagree."""
import pytest

from harness.lsp_positions import (DEFAULT_ENCODING, ENCODINGS, UTF8, UTF16,
                                   UTF32, character_of, index_of, line_starts,
                                   offset_of, position_of, slice_of,
                                   split_lines)

GRIN = "\U0001F600"  # U+1F600, one code point, two utf-16 units, four bytes
ACUTE = "é"          # one code point, one utf-16 unit, two bytes
HAN = "漢"           # one code point, one utf-16 unit, three bytes


def test_utf_16_is_the_default_both_sides_fall_back_to():
    assert DEFAULT_ENCODING == UTF16
    assert set(ENCODINGS) == {UTF8, UTF16, UTF32}


def test_every_encoding_agrees_on_ascii_which_is_why_the_bug_hides():
    line = "def total(values):"
    for index in range(len(line) + 1):
        counts = {character_of(line, index, kind) for kind in ENCODINGS}
        assert counts == {index}


def test_the_encodings_part_company_at_the_first_astral_character():
    line = f"x = '{GRIN}' + y"
    assert len(line) == 11
    assert character_of(line, 10, UTF32) == 10  # what a Python index counts
    assert character_of(line, 10, UTF16) == 11  # what a server means by default
    assert character_of(line, 10, UTF8) == 13   # what a byte-counting server means


def test_utf_8_counts_the_bytes_each_code_point_costs():
    assert character_of(ACUTE, 1, UTF8) == 2
    assert character_of(HAN, 1, UTF8) == 3
    assert character_of(GRIN, 1, UTF8) == 4


def test_utf_16_counts_two_units_only_above_the_basic_plane():
    assert character_of(ACUTE + HAN, 2, UTF16) == 2
    assert character_of(GRIN, 1, UTF16) == 2


@pytest.mark.parametrize("encoding", ENCODINGS)
def test_an_index_survives_the_trip_out_to_a_character_and_back(encoding):
    line = f"a{ACUTE}b{HAN}c{GRIN}d"
    for index in range(len(line) + 1):
        assert index_of(line, character_of(line, index, encoding),
                        encoding) == index


def test_a_character_inside_a_surrogate_pair_rounds_down_to_its_start():
    line = f"ab{GRIN}cd"
    assert index_of(line, 2, UTF16) == 2  # the pair starts here
    assert index_of(line, 3, UTF16) == 2  # halfway in, and there is no halfway
    assert index_of(line, 4, UTF16) == 3  # past it


def test_a_character_inside_a_utf_8_sequence_rounds_down_to_its_start():
    line = f"ab{HAN}cd"
    assert [index_of(line, char, UTF8) for char in (2, 3, 4, 5)] == [2, 2, 2, 3]


def test_a_character_past_the_end_of_a_line_clamps_to_the_end_of_the_line():
    line = "short"
    for encoding in ENCODINGS:
        assert index_of(line, 900, encoding) == len(line)
        assert character_of(line, 900, encoding) == len(line)


def test_a_negative_offset_is_the_start_of_the_line_rather_than_an_error():
    for encoding in ENCODINGS:
        assert index_of("abc", -4, encoding) == 0
        assert character_of("abc", -4, encoding) == 0


def test_an_encoding_nobody_negotiated_is_refused_rather_than_guessed():
    with pytest.raises(ValueError, match="position encoding"):
        character_of("a", 0, "utf-7")
    with pytest.raises(ValueError):
        offset_of("a", {"line": 0, "character": 0}, "ascii")


def test_the_three_line_terminators_split_and_nothing_else_does():
    assert split_lines("a\nb\r\nc\rd") == ["a", "b", "c", "d"]
    # str.splitlines breaks on all of these. A server does not, so a document
    # holding one would land every later line number off by one.
    for other in ("\v", "\f", "\x1c", "\x85", " ", " "):
        assert split_lines(f"a{other}b") == [f"a{other}b"]


def test_a_document_ending_in_a_break_has_an_empty_last_line():
    assert split_lines("a\n") == ["a", ""]
    assert line_starts("a\n") == [0, 2]
    assert position_of("a\n", 2, UTF16) == {"line": 1, "character": 0}


def test_a_position_names_the_same_place_the_offset_does():
    text = f"import os\ns = '{GRIN}{HAN}'\r\nprint(s)\rdone"
    unnameable = {index for index in range(1, len(text))
                  if text[index - 1] == "\r" and text[index] == "\n"}
    for encoding in ENCODINGS:
        for offset in range(len(text) + 1):
            if offset in unnameable:
                continue
            position = position_of(text, offset, encoding)
            assert offset_of(text, position, encoding) == offset


def test_the_offset_between_the_halves_of_a_crlf_is_not_a_position():
    # LSP can name the end of a line and the start of the next one, and nothing
    # between them, so this offset clamps back to the end of the line it sits
    # in. Named here so the round trip above can skip it in the open rather than
    # by quietly choosing text that has no CRLF in it.
    text = "ab\r\ncd"
    assert position_of(text, 3, UTF16) == {"line": 0, "character": 2}
    assert offset_of(text, position_of(text, 3, UTF16), UTF16) == 2


def test_a_character_past_a_line_end_does_not_walk_onto_the_next_line():
    text = "ab\ncd"
    assert offset_of(text, {"line": 0, "character": 99}, UTF16) == 2
    assert text[offset_of(text, {"line": 1, "character": 0}, UTF16)] == "c"


def test_a_line_past_the_end_of_the_document_is_the_end_of_the_document():
    text = "one\ntwo"
    assert offset_of(text, {"line": 40, "character": 0}, UTF16) == len(text)
    assert offset_of(text, {"line": -1, "character": 3}, UTF16) == 0


def test_an_offset_past_the_document_clamps_to_its_last_position():
    text = "one\ntwo"
    assert position_of(text, 99, UTF16) == {"line": 1, "character": 3}
    assert position_of(text, -5, UTF16) == {"line": 0, "character": 0}


def test_a_range_reported_in_utf_16_names_the_symbol_a_reader_would_point_at():
    # The case this whole module exists for. A server reports a diagnostic in
    # utf-16 characters; a client that reads them as Python indices highlights
    # the wrong word, and only after the file grows an emoji.
    text = f"tag = '{GRIN}'\nvlaue = tag\n"
    span = {"start": {"line": 1, "character": 0},
            "end": {"line": 1, "character": 5}}
    assert slice_of(text, span, UTF16) == "vlaue"
    assert slice_of(text, {"start": {"line": 0, "character": 7},
                          "end": {"line": 0, "character": 9}}, UTF16) == GRIN


def test_a_range_whose_end_precedes_its_start_covers_nothing():
    text = "abcdef"
    span = {"start": {"line": 0, "character": 4},
            "end": {"line": 0, "character": 1}}
    assert slice_of(text, span, UTF32) == ""


def test_a_position_with_missing_fields_reads_as_the_start_of_the_document():
    assert offset_of("abc", {}, UTF16) == 0
