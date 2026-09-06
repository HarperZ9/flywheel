"""A WorkspaceEdit against the filesystem: what is written, and what is refused.

The controls matter more than the applications here. A refusal that still wrote
the file reads identically from the caller's side, differing only in a string,
so every refusal below is checked against the bytes left on disk rather than
against the message.
"""
import os
import stat

import pytest

from harness.lsp_documents import Documents, to_uri
from harness.lsp_edits import (EditRefused, apply_plan, apply_workspace_edit,
                               plan_edit)


def span(line, start, end, new_text):
    return {"range": {"start": {"line": line, "character": start},
                      "end": {"line": line, "character": end}},
            "newText": new_text}


def write(tmp_path, name, text, newline="\n"):
    path = tmp_path / name
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text.replace("\n", newline))
    return path


def changes(path, *edits):
    return {"changes": {to_uri(path): list(edits)}}


# ── the plan, which is the half that never writes ────────────────────────────

def test_planning_leaves_the_file_exactly_as_it_was(tmp_path):
    path = write(tmp_path, "a.py", "one\ntwo\n")
    before = path.read_bytes()
    plan = plan_edit(changes(path, span(0, 0, 3, "ONE")), root=tmp_path)
    assert plan.files[0].after == "ONE\ntwo\n"
    assert path.read_bytes() == before


def test_writing_takes_a_caller_who_said_so(tmp_path):
    """Default-deny, and the file is the evidence that the deny held."""
    path = write(tmp_path, "a.py", "one\n")
    plan = plan_edit(changes(path, span(0, 0, 3, "ONE")), root=tmp_path)
    with pytest.raises(EditRefused) as caught:
        apply_plan(plan)
    assert caught.value.reason == "write-not-allowed"
    assert path.read_text(encoding="utf-8") == "one\n"


def test_an_allowed_write_lands_and_reports_both_digests(tmp_path):
    path = write(tmp_path, "a.py", "one\n")
    summary = apply_workspace_edit(changes(path, span(0, 0, 3, "ONE")),
                                   root=tmp_path, allow_write=True)
    assert path.read_text(encoding="utf-8") == "ONE\n"
    record = summary["files"][0]
    assert record["before_sha256"] != record["after_sha256"]
    assert summary["written"] == [to_uri(path)]
    assert summary["applied"] is True
    assert summary["does_not_prove"]


# ── the refusals, each checked against the disk ──────────────────────────────

def test_a_uri_outside_the_root_is_refused_before_it_is_read(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    outside = write(tmp_path, "secret.txt", "keep\n")
    with pytest.raises(EditRefused) as caught:
        apply_workspace_edit(changes(outside, span(0, 0, 4, "gone")),
                             root=root, allow_write=True)
    assert caught.value.reason == "outside-root"
    assert outside.read_text(encoding="utf-8") == "keep\n"


def test_a_uri_that_climbs_out_of_the_root_is_refused(tmp_path):
    """The same claim with traversal rather than an absolute path."""
    root = tmp_path / "workspace"
    root.mkdir()
    outside = write(tmp_path, "secret.txt", "keep\n")
    uri = to_uri(root / ".." / "secret.txt")
    with pytest.raises(EditRefused) as caught:
        apply_workspace_edit({"changes": {uri: [span(0, 0, 4, "gone")]}},
                             root=root, allow_write=True)
    assert caught.value.reason == "outside-root"
    assert outside.read_text(encoding="utf-8") == "keep\n"


def test_a_scheme_that_is_not_a_file_is_refused(tmp_path):
    with pytest.raises(EditRefused) as caught:
        plan_edit({"changes": {"https://example.invalid/a.py":
                               [span(0, 0, 1, "Z")]}}, root=tmp_path)
    assert caught.value.reason == "not-a-file-uri"


def test_a_document_that_is_not_on_disk_is_refused(tmp_path):
    uri = to_uri(tmp_path / "missing.py")
    with pytest.raises(EditRefused) as caught:
        plan_edit({"changes": {uri: [span(0, 0, 1, "Z")]}}, root=tmp_path)
    assert caught.value.reason == "no-such-file"


def test_one_bad_document_stops_the_whole_edit(tmp_path):
    """The multi-file control.

    An implementation that planned and wrote each document as it went would
    have changed the first file before reaching the second. The first file is
    what says the edit was checked whole.
    """
    good = write(tmp_path, "a.py", "one\n")
    bad = write(tmp_path, "b.py", "two\n")
    edit = {"changes": {to_uri(good): [span(0, 0, 3, "ONE")],
                        to_uri(bad): [span(0, 0, 3, "x"),
                                      span(0, 1, 3, "y")]}}
    with pytest.raises(EditRefused) as caught:
        apply_workspace_edit(edit, root=tmp_path, allow_write=True)
    assert caught.value.reason == "overlapping-edits"
    assert good.read_text(encoding="utf-8") == "one\n"
    assert bad.read_text(encoding="utf-8") == "two\n"


def test_a_resource_operation_is_refused_rather_than_performed(tmp_path):
    path = write(tmp_path, "a.py", "one\n")
    edit = {"documentChanges": [
        {"textDocument": {"uri": to_uri(path), "version": None},
         "edits": [span(0, 0, 3, "ONE")]},
        {"kind": "delete", "uri": to_uri(path)}]}
    with pytest.raises(EditRefused) as caught:
        apply_workspace_edit(edit, root=tmp_path, allow_write=True)
    assert caught.value.reason == "resource-operation"
    assert path.read_text(encoding="utf-8") == "one\n"


def test_an_edit_computed_against_an_older_buffer_is_refused(tmp_path):
    path = write(tmp_path, "a.py", "one\n")
    uri = to_uri(path)
    documents = Documents()
    documents.did_open(uri, "python", "one\n")
    documents.replace_text(uri, "edited\n")          # now at version 2
    stale = {"documentChanges": [
        {"textDocument": {"uri": uri, "version": 1},
         "edits": [span(0, 0, 3, "ONE")]}]}
    with pytest.raises(EditRefused) as caught:
        apply_workspace_edit(stale, root=tmp_path, documents=documents,
                             allow_write=True)
    assert caught.value.reason == "stale-version"
    assert path.read_text(encoding="utf-8") == "one\n"
    # The control: the same edit against the version the buffer actually holds
    # is applied, so the refusal is about the version and not about the shape.
    stale["documentChanges"][0]["textDocument"]["version"] = 2
    apply_workspace_edit(stale, root=tmp_path, documents=documents,
                         allow_write=True)
    assert path.read_text(encoding="utf-8") == "ONE\n"


def test_a_null_version_is_not_treated_as_a_stale_one(tmp_path):
    """Null means the server is not claiming to know, which is not a conflict."""
    path = write(tmp_path, "a.py", "one\n")
    uri = to_uri(path)
    documents = Documents()
    documents.did_open(uri, "python", "one\n")
    documents.replace_text(uri, "edited\n")
    apply_workspace_edit(
        {"documentChanges": [{"textDocument": {"uri": uri, "version": None},
                              "edits": [span(0, 0, 3, "ONE")]}]},
        root=tmp_path, documents=documents, allow_write=True)
    assert path.read_text(encoding="utf-8") == "ONE\n"


# ── the filesystem details that are silent when they go wrong ────────────────

def test_crlf_line_endings_survive_a_one_word_edit(tmp_path):
    """Reading in universal-newline mode would rewrite every line of the file.

    The edit touches four characters. A diff that came back showing the whole
    document would bury it, and nothing in the process would report a problem.
    """
    path = write(tmp_path, "a.py", "one\ntwo\nthree\n", newline="\r\n")
    apply_workspace_edit(changes(path, span(0, 0, 3, "ONE")), root=tmp_path,
                         allow_write=True)
    assert path.read_bytes() == b"ONE\r\ntwo\r\nthree\r\n"


def test_a_document_the_edit_did_not_change_is_not_opened_for_writing(tmp_path):
    """Proved by making the write impossible rather than by reading a flag.

    A read-only file raises on open for writing. If the skip were not real this
    would fail with write-failed, and the summary would have said `changed: 0`
    either way.
    """
    path = write(tmp_path, "a.py", "one\n")
    os.chmod(path, stat.S_IREAD)
    try:
        summary = apply_workspace_edit(changes(path, span(0, 0, 3, "one")),
                                       root=tmp_path, allow_write=True)
        assert summary["changed"] == 0
        assert summary["written"] == []
        # The control: an edit that does change the text hits the same file and
        # fails, which is what says the read-only bit was doing something.
        with pytest.raises(EditRefused) as caught:
            apply_workspace_edit(changes(path, span(0, 0, 3, "ONE")),
                                 root=tmp_path, allow_write=True)
        assert caught.value.reason == "write-failed"
    finally:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)


def test_documentchanges_is_read_when_both_shapes_are_present(tmp_path):
    """A server sending both means the same thing twice, and one shape wins."""
    path = write(tmp_path, "a.py", "one\n")
    uri = to_uri(path)
    apply_workspace_edit(
        {"changes": {uri: [span(0, 0, 3, "LEGACY")]},
         "documentChanges": [{"textDocument": {"uri": uri, "version": None},
                              "edits": [span(0, 0, 3, "MODERN")]}]},
        root=tmp_path, allow_write=True)
    assert path.read_text(encoding="utf-8") == "MODERN\n"
