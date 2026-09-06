"""Who owns an open document, at which version, and under which URI."""
from pathlib import Path

import pytest

from harness.lsp_documents import (Documents, UnknownDocument, apply_change,
                                   from_uri, to_uri)
from harness.lsp_positions import UTF8, UTF16, UTF32

GRIN = "\U0001F600"


def span(start_line, start_char, end_line, end_char):
    return {"start": {"line": start_line, "character": start_char},
            "end": {"line": end_line, "character": end_char}}


def edit(start_line, start_char, end_line, end_char, text):
    """One incremental content change over the range those four numbers name."""
    return {"range": span(start_line, start_char, end_line, end_char),
            "text": text}


def test_a_path_survives_the_trip_out_to_a_uri_and_back(tmp_path):
    location = tmp_path / "sub dir" / "módulo.py"
    location.parent.mkdir()
    location.write_text("x = 1\n", encoding="utf-8")
    uri = to_uri(location)
    assert uri.startswith("file:///")
    assert from_uri(uri) == location.resolve()


def test_a_uri_names_a_file_and_a_uri_that_does_not_is_refused():
    with pytest.raises(ValueError, match="file URI"):
        from_uri("https://example.invalid/x.py")


def test_a_windows_path_keeps_its_drive_and_its_separators(tmp_path):
    # A wrong file URI is not an error on the wire. The server answers about a
    # document it has never seen, the answer is an empty list, and an empty list
    # reads exactly like a clean file.
    text = to_uri(tmp_path / "a.py")
    assert " " not in text and "\\" not in text
    assert from_uri(text).name == "a.py"


def test_opening_a_document_starts_it_at_version_one():
    store = Documents()
    params = store.did_open("file:///a.py", "python", "x = 1\n")
    assert params["textDocument"]["version"] == 1
    assert params["textDocument"]["languageId"] == "python"
    assert store.get("file:///a.py").text == "x = 1\n"


def test_opening_the_same_document_twice_is_refused():
    store = Documents()
    store.did_open("file:///a.py", "python", "")
    with pytest.raises(ValueError, match="already open"):
        store.did_open("file:///a.py", "python", "")


def test_a_document_this_client_never_opened_is_named_rather_than_guessed():
    store = Documents()
    with pytest.raises(UnknownDocument, match="not open"):
        store.get("file:///gone.py")
    with pytest.raises(UnknownDocument):
        store.did_change("file:///gone.py", [{"text": "x"}])
    with pytest.raises(UnknownDocument):
        store.did_close("file:///gone.py")


def test_reading_a_file_from_disk_opens_it_under_its_own_uri(tmp_path):
    location = tmp_path / "m.py"
    location.write_text("import os\n", encoding="utf-8")
    store = Documents()
    params = store.open_path(location, "python")
    assert params["textDocument"]["uri"] == to_uri(location)
    assert params["textDocument"]["text"] == "import os\n"


def test_every_change_moves_the_version_forward():
    store = Documents()
    store.did_open("file:///a.py", "python", "a\n")
    assert store.replace_text("file:///a.py", "b\n")["textDocument"][
        "version"] == 2
    assert store.replace_text("file:///a.py", "c\n")["textDocument"][
        "version"] == 3
    assert store.get("file:///a.py").text == "c\n"


def test_a_change_with_no_range_replaces_the_whole_document():
    assert apply_change("old text", {"text": "new"}, UTF16) == "new"


def test_a_change_with_a_range_replaces_only_that_range():
    text = "alpha\nbeta\ngamma\n"
    changed = apply_change(text, edit(1, 0, 1, 4, "BETA"), UTF16)
    assert changed == "alpha\nBETA\ngamma\n"


def test_an_insertion_is_a_range_of_width_zero():
    changed = apply_change("ac", edit(0, 1, 0, 1, "b"), UTF16)
    assert changed == "abc"


def test_a_deletion_is_a_range_with_no_replacement_text():
    changed = apply_change("abc", edit(0, 1, 0, 2, ""), UTF16)
    assert changed == "ac"


def test_a_change_range_is_read_in_the_negotiated_encoding():
    # The same numbers name different text under different encodings, which is
    # the whole reason the store is told which one was negotiated.
    text = f"{GRIN}xy"
    change = edit(0, 2, 0, 3, "Z")
    assert apply_change(text, change, UTF16) == f"{GRIN}Zy"
    assert apply_change(text, change, UTF32) == f"{GRIN}xZ"
    # Under utf-8 both endpoints land inside the emoji's four bytes and round
    # down to its start, so the same two numbers describe an insertion in front
    # of it rather than a replacement of anything.
    assert apply_change(text, change, UTF8) == f"Z{GRIN}xy"


def test_a_change_without_text_is_refused_rather_than_treated_as_a_deletion():
    with pytest.raises(ValueError, match="carries the text"):
        apply_change("abc", span(0, 0, 0, 1), UTF16)


def test_a_change_range_that_ends_before_it_starts_is_refused():
    with pytest.raises(ValueError, match="ends before it starts"):
        apply_change("abcdef", edit(0, 4, 0, 1, "x"), UTF16)


def test_changes_in_one_notification_apply_in_the_order_they_are_listed():
    # Each change describes the text the ones before it left behind. Applying
    # them in any other order corrupts the client's copy while the server's
    # copy stays right, which is the hardest kind of drift to notice.
    store = Documents()
    store.did_open("file:///a.py", "python", "abc")
    store.did_change("file:///a.py", [edit(0, 0, 0, 1, "XY"),
                                      edit(0, 0, 0, 2, "z")])
    assert store.get("file:///a.py").text == "zbc"


def test_a_stamp_says_which_version_an_answer_was_taken_at():
    store = Documents()
    store.did_open("file:///a.py", "python", "one\ntwo\n")
    stamp = store.stamp("file:///a.py")
    assert stamp == {"uri": "file:///a.py", "version": 1,
                     "characters": 8, "lines": 3}


def test_an_answer_taken_before_an_edit_is_no_longer_current_after_it():
    store = Documents()
    store.did_open("file:///a.py", "python", "one\n")
    asked_at = store.stamp("file:///a.py")["version"]
    assert store.is_current("file:///a.py", asked_at)
    store.replace_text("file:///a.py", "two\n")
    assert not store.is_current("file:///a.py", asked_at)


def test_a_closed_document_is_not_current_at_any_version():
    store = Documents()
    store.did_open("file:///a.py", "python", "one\n")
    store.did_close("file:///a.py")
    assert not store.is_current("file:///a.py", 1)
    assert "file:///a.py" not in store


def test_closing_everything_leaves_nothing_half_owned():
    store = Documents()
    for name in ("a", "b", "c"):
        store.did_open(f"file:///{name}.py", "python", "")
    assert len(store) == 3
    closed = store.close_all()
    assert [entry["textDocument"]["uri"] for entry in closed] == [
        "file:///a.py", "file:///b.py", "file:///c.py"]
    assert len(store) == 0


def test_the_change_notification_carries_the_version_it_produced():
    store = Documents()
    store.did_open("file:///a.py", "python", "a\n")
    params = store.did_change("file:///a.py", [{"text": "b\n"}])
    assert params["textDocument"] == {"uri": "file:///a.py", "version": 2}
    assert params["contentChanges"] == [{"text": "b\n"}]


def test_a_unc_uri_keeps_both_leading_separators():
    assert str(from_uri("file://server/share/x.py")).replace(
        "\\", "/") == "//server/share/x.py"


def test_a_document_read_from_disk_matches_what_was_written(tmp_path):
    location = Path(tmp_path) / "u.py"
    location.write_text(f"s = '{GRIN}'\n", encoding="utf-8")
    store = Documents()
    store.open_path(location, "python")
    assert store.get(to_uri(location)).text == f"s = '{GRIN}'\n"
