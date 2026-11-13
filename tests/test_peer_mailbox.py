"""File mailbox: body hash on every message, drift detected, nothing overwritten."""
from __future__ import annotations

import hashlib
import json
import os

import pytest

from harness import peer_mailbox as mb

SENT = "2026-09-10T18:30:00Z"
BODY = "status: slice one drafted\nnext: tests\n"


def _box(tmp_path):
    box = tmp_path / "mailbox"
    box.mkdir()
    return box


def test_write_then_read_round_trip_matches(tmp_path):
    box = _box(tmp_path)
    record = mb.write_message(box, sender="claude.fable", to="codex.root", body=BODY,
                              sent_utc=SENT)
    name = "claude.fable-to-codex.root-20260910T183000Z.md"
    assert record["file_name"] == name and (box / name).is_file()
    assert record["receipt_state"] == "MATCH"
    assert record["from"] == "claude.fable" and record["to"] == "codex.root"
    assert record["sent_utc"] == SENT and record["in_reply_to"] is None
    assert record["body"] == BODY and record["body_chars"] == len(BODY)
    assert record["body_sha256_declared"] == hashlib.sha256(BODY.encode()).hexdigest()
    assert record["body_sha256_computed"] == record["body_sha256_declared"]
    assert record["file_name_consistent"] is True
    assert record["schema"] == "flywheel.peer-mailbox-message/v1"
    assert "does not prove who wrote it" in record["does_not_prove"]


def test_render_has_fixed_header_block_and_trailing_newline():
    text = mb.render(sender="a", to="b", sent_utc=SENT, body="hello", in_reply_to=None)
    digest = hashlib.sha256(b"hello\n").hexdigest()
    assert text == f"from: a\nto: b\nsent_utc: {SENT}\nin_reply_to: none\nbody_sha256: {digest}\n\nhello\n"
    assert mb.parse(text)["receipt_state"] == "MATCH"
    assert mb.parse(text)["body"] == "hello\n"
    assert mb.render(sender="a", to="b", sent_utc=SENT, body="hello\n", in_reply_to=None) == text


def test_edited_body_is_reported_as_drift_not_raised(tmp_path):
    box = _box(tmp_path)
    record = mb.write_message(box, sender="a", to="b", body=BODY, sent_utc=SENT)
    path = box / record["file_name"]
    path.write_bytes(path.read_bytes().replace(b"tests", b"nothing"))
    drifted = mb.read_message(path)
    assert drifted["receipt_state"] == "DRIFT"
    assert drifted["body_sha256_declared"] == record["body_sha256_declared"]
    assert drifted["body_sha256_computed"] != record["body_sha256_declared"]


def test_same_stamp_is_refused_never_overwritten(tmp_path):
    box = _box(tmp_path)
    mb.write_message(box, sender="a", to="b", body="first", sent_utc=SENT)
    with pytest.raises(FileExistsError):
        mb.write_message(box, sender="a", to="b", body="second", sent_utc=SENT)
    assert mb.read_message(box / "a-to-b-20260910T183000Z.md")["body"] == "first\n"


@pytest.mark.parametrize("bad", ["", "a-to-b", "with space", "x" * 65, "-lead", 7, None])
def test_bad_identifiers_are_refused(tmp_path, bad):
    box = _box(tmp_path)
    with pytest.raises(mb.MailboxError):
        mb.write_message(box, sender=bad, to="b", body=BODY, sent_utc=SENT)
    with pytest.raises(mb.MailboxError):
        mb.write_message(box, sender="a", to=bad, body=BODY, sent_utc=SENT)
    assert list(box.iterdir()) == []


@pytest.mark.parametrize("bad", ["", "   \n", 12, None])
def test_empty_or_non_text_body_is_refused(tmp_path, bad):
    with pytest.raises(mb.MailboxError):
        mb.write_message(_box(tmp_path), sender="a", to="b", body=bad, sent_utc=SENT)


def test_oversize_message_is_refused_before_writing(tmp_path):
    box = _box(tmp_path)
    with pytest.raises(mb.MailboxError):
        mb.write_message(box, sender="a", to="b", body="x" * (mb.MAX_MESSAGE_BYTES + 1),
                         sent_utc=SENT)
    assert list(box.iterdir()) == []


@pytest.mark.parametrize("bad", ["2026-09-10T18:30:00", "not a time", "", None])
def test_sent_utc_must_be_zoned_iso(tmp_path, bad):
    with pytest.raises(mb.MailboxError):
        mb.write_message(_box(tmp_path), sender="a", to="b", body=BODY, sent_utc=bad)


def test_non_utc_offset_is_normalised_in_the_file_name(tmp_path):
    record = mb.write_message(_box(tmp_path), sender="a", to="b", body=BODY,
                              sent_utc="2026-09-10T11:30:00-07:00")
    assert record["file_name"] == "a-to-b-20260910T183000Z.md"
    assert record["sent_utc"] == "2026-09-10T11:30:00-07:00"


def test_in_reply_to_must_name_a_mailbox_file(tmp_path):
    box = _box(tmp_path)
    first = mb.write_message(box, sender="a", to="b", body=BODY, sent_utc=SENT)
    with pytest.raises(mb.MailboxError):
        mb.write_message(box, sender="b", to="a", body=BODY, sent_utc="2026-09-10T18:31:00Z",
                         in_reply_to="../outside.md")
    reply = mb.write_message(box, sender="b", to="a", body=BODY, sent_utc="2026-09-10T18:31:00Z",
                             in_reply_to=first["file_name"])
    assert reply["in_reply_to"] == first["file_name"]


def test_listing_is_hash_only_by_default_and_reports_malformed_files(tmp_path):
    box = _box(tmp_path)
    secret = "CANARY-BODY-NOT-IN-LISTING"
    mb.write_message(box, sender="a", to="b", body=secret, sent_utc="2026-09-10T18:32:00Z")
    mb.write_message(box, sender="b", to="a", body=BODY, sent_utc=SENT)
    (box / "c-to-d-20260910T180000Z.md").write_text("no header here\n", encoding="utf-8")
    (box / "README.md").write_text(secret, encoding="utf-8")
    (box / "a-to-b-20260910T183500Z.md").write_bytes(b"from: a\nto: b\n\xff\xfe\n\nx\n")
    rows = mb.list_messages(box)
    assert [r["file_name"] for r in rows] == ["c-to-d-20260910T180000Z.md",
                                              "b-to-a-20260910T183000Z.md",
                                              "a-to-b-20260910T183200Z.md",
                                              "a-to-b-20260910T183500Z.md"]
    assert rows[0] == {"schema": "flywheel.peer-mailbox-message/v1",
                       "file_name": "c-to-d-20260910T180000Z.md",
                       "receipt_state": "UNVERIFIABLE", "error": "unreadable_or_malformed"}
    assert rows[3]["receipt_state"] == "UNVERIFIABLE"
    assert rows[1]["receipt_state"] == "MATCH" and rows[2]["receipt_state"] == "MATCH"
    assert secret not in json.dumps(rows)
    with_body = mb.list_messages(box, include_body=True)
    assert with_body[2]["body"] == secret + "\n"


@pytest.mark.parametrize("text", [
    "from: a\nto: b\nsent_utc: x\nin_reply_to: none\nbody_sha256: 0\nbody without blank line",
    "from: a\nfrom: a\nto: b\nsent_utc: x\nin_reply_to: none\nbody_sha256: 0\n\nx\n",
    "from: a\nto: b\nsent_utc: x\nin_reply_to: none\n\nx\n",
    "from: a\nto: b\nsent_utc: x\nin_reply_to: none\nbody_sha256: 0\nextra: y\n\nx\n",
    "from: a-to-b\nto: b\nsent_utc: x\nin_reply_to: none\nbody_sha256: 0\n\nx\n",
    "",
])
def test_parse_rejects_malformed_headers(text):
    with pytest.raises(mb.MailboxError):
        mb.parse(text)


def test_parse_flags_file_name_that_disagrees_with_headers():
    text = mb.render(sender="a", to="b", sent_utc=SENT, body="x", in_reply_to=None)
    assert mb.parse(text, file_name="a-to-b-20260910T183000Z.md")["file_name_consistent"] is True
    assert mb.parse(text, file_name="b-to-a-20260910T183000Z.md")["file_name_consistent"] is False
    assert mb.parse(text, file_name="weird.md")["file_name_consistent"] is False
    assert "file_name_consistent" not in mb.parse(text)


def test_read_message_refuses_symlink_oversize_and_missing(tmp_path):
    box = _box(tmp_path)
    record = mb.write_message(box, sender="a", to="b", body=BODY, sent_utc=SENT)
    real = box / record["file_name"]
    big = box / "a-to-b-20260910T190000Z.md"
    big.write_bytes(b"x" * (mb.MAX_MESSAGE_BYTES + 1))
    with pytest.raises(mb.MailboxError):
        mb.read_message(big)
    with pytest.raises(mb.MailboxError):
        mb.read_message(box / "absent.md")
    link = box / "a-to-b-20260910T190100Z.md"
    try:
        os.symlink(real, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted here")
    with pytest.raises(mb.MailboxError):
        mb.read_message(link)
    assert [r["receipt_state"] for r in mb.list_messages(box)] == ["MATCH", "UNVERIFIABLE",
                                                                   "UNVERIFIABLE"]


def test_mailbox_must_be_an_existing_directory(tmp_path):
    with pytest.raises(mb.MailboxError):
        mb.write_message(tmp_path / "nope", sender="a", to="b", body=BODY, sent_utc=SENT)
    with pytest.raises(mb.MailboxError):
        mb.list_messages(tmp_path / "nope")


def test_a_body_holding_carriage_returns_round_trips_without_translation(tmp_path):
    """The hash covers the body's bytes as they sit on disk. A body that carries
    CRLF of its own has to read back as MATCH, with those bytes unchanged."""
    box = _box(tmp_path)
    body = "line one\r\nline two\rtail\n"
    record = mb.write_message(box, sender="a", to="b", body=body, sent_utc=SENT)
    path = box / record["file_name"]
    assert path.read_bytes().endswith(b"\n\nline one\r\nline two\rtail\n")
    assert record["receipt_state"] == "MATCH" and record["body"] == body
    assert record["body_sha256_computed"] == hashlib.sha256(body.encode()).hexdigest()
    assert mb.read_message(path)["receipt_state"] == "MATCH"


def test_a_file_rewritten_with_crlf_endings_reports_drift(tmp_path):
    """A copy that passed through a newline-translating editor is a changed file.
    Reporting MATCH there would hide a rewrite the reader has no other way to see."""
    box = _box(tmp_path)
    record = mb.write_message(box, sender="a", to="b", body=BODY, sent_utc=SENT)
    path = box / record["file_name"]
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    rewritten = mb.read_message(path)
    assert rewritten["receipt_state"] == "DRIFT"
    assert rewritten["body_sha256_declared"] == record["body_sha256_declared"]
    assert rewritten["from"] == "a" and rewritten["to"] == "b"
    assert rewritten["file_name_consistent"] is True
    assert mb.list_messages(box)[0]["receipt_state"] == "DRIFT"
