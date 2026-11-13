"""File mailbox between agent sessions, with a body hash on every message.

Sessions on one machine (a Claude Code session, two Codex threads) share no
message API, and injecting a turn into another operator-owned session is
out of bounds. A directory of small files is the channel. One message is
one file named <from>-to-<to>-<UTC stamp>.md with a fixed header block:

    from: <sender>
    to: <recipient>
    sent_utc: <ISO-8601 Z>
    in_reply_to: <file name or "none">
    body_sha256: <hex>

    <body>

The hash covers the body's bytes exactly as they sit on disk. Reading never
translates line endings, so a file rewritten with CRLF reports DRIFT instead
of passing as MATCH, and a body that legitimately carries a carriage return
still round-trips. A message is evidence that a file was written, never an
instruction to act.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re

from .peer_session_types import MAILBOX_SCHEMA

HEADER_KEYS = ("from", "to", "sent_utc", "in_reply_to", "body_sha256")
IDENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._]{0,63}\Z")
STAMP = re.compile(r"\d{8}T\d{6}Z\Z")
HEX64 = re.compile(r"[0-9a-fA-F]{64}\Z")
FILE_NAME = re.compile(r"(?P<sender>[A-Za-z0-9][A-Za-z0-9._]{0,63})-to-"
                       r"(?P<to>[A-Za-z0-9][A-Za-z0-9._]{0,63})-(?P<stamp>\d{8}T\d{6}Z)\.md\Z")
MAX_MESSAGE_BYTES = 262_144
MAX_LISTING = 4096


class MailboxError(ValueError):
    """The mailbox input is malformed or outside the allowed shape."""


def _ident(value: object, field: str) -> str:
    if type(value) is not str or not IDENT.match(value) or "-to-" in value:
        raise MailboxError(f"{field} must be a short identifier without '-to-'")
    return value


def _stamp(sent_utc: object) -> str:
    if type(sent_utc) is not str:
        raise MailboxError("sent_utc must be an ISO-8601 string")
    try:
        moment = datetime.fromisoformat(sent_utc.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MailboxError("sent_utc must be ISO-8601") from exc
    if moment.tzinfo is None:
        raise MailboxError("sent_utc must carry a timezone")
    return moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _reply_ref(value: object) -> str:
    if value == "none":
        return "none"
    if type(value) is not str or not FILE_NAME.match(value):
        raise MailboxError("in_reply_to must name a mailbox file or be 'none'")
    return value


def body_sha256(body: str | bytes) -> str:
    """Hash the body's bytes. A str is encoded UTF-8 with no newline translation."""
    raw = body.encode("utf-8") if type(body) is str else bytes(body)
    return hashlib.sha256(raw).hexdigest()


def render(*, sender: str, to: str, sent_utc: str, body: str, in_reply_to: str | None) -> str:
    _ident(sender, "from"), _ident(to, "to"), _stamp(sent_utc)
    if type(body) is not str or not body.strip():
        raise MailboxError("body must be non-empty text")
    reply = _reply_ref("none" if in_reply_to is None else in_reply_to)
    if not body.endswith("\n"):
        body += "\n"
    head = [f"from: {sender}", f"to: {to}", f"sent_utc: {sent_utc}",
            f"in_reply_to: {reply}", f"body_sha256: {body_sha256(body)}"]
    return "\n".join(head) + "\n\n" + body


def write_message(mailbox: str | os.PathLike[str], *, sender: str, to: str, body: str,
                  sent_utc: str, in_reply_to: str | None = None) -> dict:
    """Write one message file. Refuses to overwrite. Returns the parsed record."""
    root = Path(mailbox)
    if root.is_symlink() or not root.is_dir():
        raise MailboxError("mailbox must be an existing directory")
    name = f"{_ident(sender, 'from')}-to-{_ident(to, 'to')}-{_stamp(sent_utc)}.md"
    text = render(sender=sender, to=to, sent_utc=sent_utc, body=body, in_reply_to=in_reply_to)
    data = text.encode("utf-8")
    if len(data) > MAX_MESSAGE_BYTES:
        raise MailboxError("message too large")
    target = root / name
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    return read_message(target)


def _split(raw: bytes) -> tuple[bytes, bytes]:
    """Header bytes and body bytes, split at the first blank line. LF is canonical;
    a CRLF blank line is accepted so a rewritten file reports DRIFT, not nothing."""
    lf = raw.find(b"\n\n")
    crlf = raw.find(b"\r\n\r\n")
    if crlf >= 0 and (lf < 0 or crlf < lf):
        return raw[:crlf], raw[crlf + 4:]
    if lf >= 0:
        return raw[:lf], raw[lf + 2:]
    raise MailboxError("message lacks the blank line after the header")


def _headers(head: bytes) -> dict[str, str]:
    try:
        text = head.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MailboxError("header is not UTF-8") from exc
    headers: dict[str, str] = {}
    for line in text.split("\n"):
        key, colon, value = line.rstrip("\r").partition(":")
        if not colon or key not in HEADER_KEYS or key in headers:
            raise MailboxError("malformed header line")
        headers[key] = value.strip()
    if set(headers) != set(HEADER_KEYS):
        raise MailboxError("header keys missing")
    return headers


def parse(data: str | bytes, *, file_name: str | None = None) -> dict:
    """Parse one message and check its body hash. Never raises on drift alone.

    The hash is taken over the body's bytes, so the record states what the file
    holds rather than what a newline-translating reader would have produced.
    """
    raw = data.encode("utf-8") if type(data) is str else bytes(data)
    head, body_bytes = _split(raw)
    headers = _headers(head)
    _ident(headers["from"], "from"), _ident(headers["to"], "to")
    _stamp(headers["sent_utc"])
    reply = _reply_ref(headers["in_reply_to"])
    declared = headers["body_sha256"]
    if not HEX64.match(declared):
        raise MailboxError("body_sha256 must be 64 hex characters")
    try:
        body = body_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MailboxError("body is not UTF-8") from exc
    computed = hashlib.sha256(body_bytes).hexdigest()
    state = "MATCH" if computed == declared.lower() else "DRIFT"
    record = {"schema": MAILBOX_SCHEMA, "file_name": file_name, "from": headers["from"],
              "to": headers["to"], "sent_utc": headers["sent_utc"],
              "in_reply_to": None if reply == "none" else reply,
              "body_sha256_declared": declared.lower(), "body_sha256_computed": computed,
              "receipt_state": state, "body_chars": len(body),
              "body_bytes": len(body_bytes), "body": body,
              "scope": "Covers the bytes of this message file. Its author and the truth "
                       "of its claims are unverified."}
    if file_name is not None:
        match = FILE_NAME.match(file_name)
        record["file_name_consistent"] = bool(match and match["sender"] == headers["from"]
                                              and match["to"] == headers["to"])
    return record


def read_message(path: str | os.PathLike[str]) -> dict:
    p = Path(path)
    if p.is_symlink() or not p.is_file():
        raise MailboxError("message must be a regular file")
    if p.stat().st_size > MAX_MESSAGE_BYTES:
        raise MailboxError("message too large")
    return parse(p.read_bytes(), file_name=p.name)


def _row(entry: Path, *, include_body: bool) -> dict:
    try:
        record = read_message(entry)
    except (MailboxError, OSError, UnicodeDecodeError):
        record = {"schema": MAILBOX_SCHEMA, "file_name": entry.name,
                  "receipt_state": "UNVERIFIABLE", "error": "unreadable_or_malformed"}
    if not include_body:
        record.pop("body", None)
    return record


def listing(mailbox: str | os.PathLike[str], *, include_body: bool = False,
            limit: int = MAX_LISTING) -> dict:
    """Bounded listing with its own omission count.

    Well-named files are selected first, ordered by the stamp in the name, and
    only then cut to `limit`, so a directory holding more files than the cap
    cannot hide the newest message behind alphabetical noise.
    """
    root = Path(mailbox)
    if root.is_symlink() or not root.is_dir():
        raise MailboxError("mailbox must be an existing directory")
    if type(limit) is not int or limit < 0:
        raise MailboxError("limit must be a non-negative int")
    named = []
    skipped = 0
    for entry in root.iterdir():
        match = FILE_NAME.match(entry.name)
        if match is None:
            skipped += 1
            continue
        named.append((match["stamp"], entry.name, entry))
    named.sort(key=lambda item: (item[0], item[1]))
    kept = named[:limit]
    rows = [_row(entry, include_body=include_body) for _stamp_, _name, entry in kept]
    return {"schema": MAILBOX_SCHEMA, "mailbox": str(root), "messages": rows,
            "listed": len(rows), "matched": len(named), "limit": limit,
            "omitted_over_limit": len(named) - len(kept), "skipped_unnamed": skipped,
            "scope": "Covers which files were present at read time. Who wrote them and "
                     "whether a reply is owed are unverified."}


def list_messages(mailbox: str | os.PathLike[str], *, include_body: bool = False,
                  limit: int = MAX_LISTING) -> list[dict]:
    """Every well-named message, oldest first. Malformed files are reported, not raised."""
    return listing(mailbox, include_body=include_body, limit=limit)["messages"]


__all__ = ["MAX_LISTING", "MAX_MESSAGE_BYTES", "MailboxError", "body_sha256", "listing",
           "list_messages", "parse", "read_message", "render", "write_message"]
