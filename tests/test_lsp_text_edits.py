"""Applying a server's TextEdits to a string, and the two silent ways it fails.

Both failures here produce a document that parses. Nothing raises, nothing logs,
and the file is wrong. That is why the falsifiers are written as comparisons
against the text the edits actually describe rather than as shape checks on the
call.
"""
import pytest

from harness.lsp_positions import UTF8, UTF16
from harness.lsp_text_edits import EditRefused, apply_text_edits

#: One line holding a character outside the basic plane. Python counts the `b`
#: at index 6, utf-16 counts it at character 7, utf-8 at character 9.
ASTRAL = 'q = "\U0001f600b"\n'


def span(line, start, end, new_text):
    return {"range": {"start": {"line": line, "character": start},
                      "end": {"line": line, "character": end}},
            "newText": new_text}


def test_a_later_edit_is_not_measured_against_an_earlier_ones_text():
    """The offset-shift falsifier.

    The first edit is eight characters longer than what it replaces. Applied one
    after another to text the previous edit already changed, the second lands
    eight characters early and eats the space. Both results are valid strings
    and only one of them is what the server asked for.
    """
    text = "aaaa bbbb\n"
    out = apply_text_edits(text, [span(0, 0, 4, "xxxxxxxxxxxx"),
                                  span(0, 5, 9, "yy")])
    assert out == "xxxxxxxxxxxx yy\n"


def test_the_array_order_of_the_edits_does_not_change_the_result():
    """A server may send them in any order, and the spec fixes the meaning."""
    text = "aaaa bbbb\n"
    forward = apply_text_edits(text, [span(0, 0, 4, "xxxxxxxxxxxx"),
                                      span(0, 5, 9, "yy")])
    reverse = apply_text_edits(text, [span(0, 5, 9, "yy"),
                                      span(0, 0, 4, "xxxxxxxxxxxx")])
    assert forward == reverse


def test_a_utf16_range_read_as_utf8_lands_somewhere_else():
    """The encoding falsifier.

    Character 7 on this line is the letter after the emoji when characters are
    utf-16 code units, and a byte in the middle of the emoji when they are utf-8
    bytes. A position inside a code point rounds down, so the utf-8 reading
    produces a document rather than an error: the letter is inserted before the
    emoji and the one the server meant to replace is still there.
    """
    edit = [span(0, 7, 8, "Z")]
    assert apply_text_edits(ASTRAL, edit, UTF16) == 'q = "\U0001f600Z"\n'
    wrong = apply_text_edits(ASTRAL, edit, UTF8)
    assert wrong != 'q = "\U0001f600Z"\n'
    assert wrong == 'q = "Z\U0001f600b"\n'


def test_several_inserts_at_one_offset_land_in_array_order():
    """The spec's one ordering rule for edits sharing a start position."""
    out = apply_text_edits("ab\n", [span(0, 1, 1, "one"), span(0, 1, 1, "two"),
                                    span(0, 1, 1, "three")])
    assert out == "aonetwothreeb\n"


def test_two_edits_claiming_the_same_character_are_refused():
    with pytest.raises(EditRefused) as caught:
        apply_text_edits("aaaa\n", [span(0, 0, 3, "x"), span(0, 2, 4, "y")])
    assert caught.value.reason == "overlapping-edits"


def test_an_edit_starting_where_the_last_one_ended_is_allowed():
    """The control on the overlap check, which would otherwise be too strict.

    Adjacent edits are the normal case for a rename touching two symbols on one
    line. A check written as `start <= reached` instead of `start < reached`
    would refuse every one of them and the refusal would look principled.
    """
    assert apply_text_edits("aabb\n", [span(0, 0, 2, "x"),
                                       span(0, 2, 4, "y")]) == "xy\n"


def test_a_backwards_range_is_read_as_the_span_it_covers():
    assert apply_text_edits("abcd\n", [span(0, 3, 1, "Z")]) == "aZd\n"


def test_an_edit_needing_confirmation_is_refused():
    edits = [dict(span(0, 0, 1, "Z"), annotationId="risky")]
    notes = {"risky": {"label": "renames a public name",
                       "needsConfirmation": True}}
    with pytest.raises(EditRefused) as caught:
        apply_text_edits("abc\n", edits, UTF16, notes)
    assert caught.value.reason == "needs-confirmation"
    assert "renames a public name" in caught.value.detail
    # And the same edit goes through once the annotation has been agreed to,
    # so the refusal is a gate and not a wall.
    assert apply_text_edits("abc\n", edits, UTF16, notes,
                            confirmed=["risky"]) == "Zbc\n"


def test_an_annotation_that_does_not_need_confirmation_is_not_a_refusal():
    edit = [dict(span(0, 0, 1, "Z"), annotationId="tidy")]
    notes = {"tidy": {"label": "reflows a comment"}}
    assert apply_text_edits("abc\n", edit, UTF16, notes) == "Zbc\n"


def test_an_edit_that_is_not_an_object_is_refused_by_name():
    with pytest.raises(EditRefused) as caught:
        apply_text_edits("abc\n", ["newText"])
    assert caught.value.reason == "malformed-edit"


def test_no_edits_leaves_the_document_exactly_as_it_was():
    assert apply_text_edits(ASTRAL, []) == ASTRAL
