"""Shared builders for the context purge, salted put and retention tests.

Payloads use placeholder text. Canaries are made at run time and exist only in
the temporary database a test creates. A residual scan looks for every 16-byte
window of a canary in each byte form it could take on disk, not only for the
whole string, because SQLite splits a long value across overflow pages.
"""
from __future__ import annotations

import base64
import hashlib
import json
import random
import secrets
import sqlite3
import unicodedata
from pathlib import Path

WORKSPACE, PROJECT = "cdev", "canon"
_ACCENTED = "éñÅüçø"  # precomposed; NFD splits each one


def prompt_payload(event_id: str = "turn-1", text: str = "Discuss Canon shared context",
                   *, session: str = "s-1", source_app: str = "codex",
                   extra_sources: list | None = None) -> dict:
    """A prompt event with one extraction and one interpretation, so an ingest
    stores three records: the event and two derived records."""
    sources = [{"source_id": "prompt", "source_kind": "prompt",
                "locator": f"{source_app}:{event_id}", "extraction_status": "completed"}]
    return {"workspace_id": WORKSPACE, "project_id": PROJECT, "event": {
        "event_id": event_id, "source_app": source_app, "native_id": event_id,
        "session_id": session, "message_text": text,
        "sources": sources + list(extra_sources or []),
        "extractions": [{"source_id": "prompt", "text": text,
                         "claim_state": "reported_by_source", "extraction_status": "completed"}],
        "interpretations": [{"text": "A coverage note about this prompt.",
                             "status": "capture_coverage_note", "source_ids": ["prompt"]}],
    }}


def answer_payload(prompt_record_id: str, prompt_native_id: str, text: str, *,
                   segment: int = 1, session: str = "s-1", source_app: str = "codex") -> dict:
    """The assistant event that answers a prompt: the pairing a purge follows."""
    return {"workspace_id": WORKSPACE, "project_id": PROJECT, "event": {
        "event_id": f"{prompt_native_id}-response-{segment}", "source_app": source_app,
        "native_id": prompt_native_id, "session_id": session, "message_text": text,
        "message_role": "assistant", "responds_to": prompt_record_id,
        "sources": [{"source_id": "prompt_event", "source_kind": "canon_event_ref",
                     "ref": prompt_record_id, "extraction_status": "completed"}],
    }}


def citing_payload(event_id: str, cited_record_id: str, text: str) -> dict:
    """A later event that cites an earlier one by record id."""
    cite = {"source_id": "earlier", "source_kind": "canon_event_ref",
            "ref": cited_record_id, "extraction_status": "completed"}
    return prompt_payload(event_id, text, extra_sources=[cite])


def short_canary() -> str:
    return "cnry" + secrets.token_hex(10)


def long_canary(min_chars: int = 10 * 1024) -> str:
    """Random text over 10 KiB, with letters whose NFC and NFD forms differ."""
    rng = random.Random(secrets.randbits(64))
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 " + _ACCENTED
    text = "".join(rng.choice(alphabet) for _ in range(min_chars + 64))
    return unicodedata.normalize("NFC", text)


def byte_forms(text: str) -> list[bytes]:
    """Every form the text can take in the files: raw UTF-8 and UTF-16LE, the
    JSON-escaped forms a record envelope uses, and base64 of the UTF-8 at each
    of its three alignments, each in NFC and NFD."""
    forms = []
    for norm in ("NFC", "NFD"):
        value = unicodedata.normalize(norm, text)
        raw = value.encode("utf-8")
        forms.append(raw)
        forms.append(value.encode("utf-16-le"))
        forms.append(json.dumps(value)[1:-1].encode("ascii"))
        forms.append(json.dumps(value, ensure_ascii=False)[1:-1].encode("utf-8"))
        forms.extend(_base64_forms(raw))
    return forms


def _base64_forms(raw: bytes) -> list[bytes]:
    """base64 of `raw` starting at each byte offset modulo three. The first
    four characters of a shifted encoding mix in the padding bytes, so they
    are dropped."""
    return [base64.b64encode(b"\x00" * shift + raw)[4 if shift else 0:] for shift in range(3)]


def db_files(db: Path) -> list[Path]:
    candidates = [db] + [Path(str(db) + suffix) for suffix in ("-journal", "-wal", "-shm")]
    return [path for path in candidates if path.exists()]


def window_hits(files: list[Path], text: str, width: int = 16) -> int:
    """How many 16-byte windows of any form of `text` occur in the files."""
    windows = set()
    for path in files:
        data = path.read_bytes()
        windows.update(data[i:i + width] for i in range(len(data) - width + 1))
    hits = 0
    for form in byte_forms(text):
        hits += sum(1 for i in range(len(form) - width + 1) if form[i:i + width] in windows)
    return hits


def rows(db: Path, sql: str, params: tuple = ()) -> list[tuple]:
    con = sqlite3.connect(str(db))
    try:
        return con.execute(sql, params).fetchall()
    finally:
        con.close()


def record_keys(db: Path) -> set[str]:
    return {row[0] for row in rows(db, "SELECT key FROM records")}


def counts(db: Path) -> tuple[int, int]:
    return (rows(db, "SELECT COUNT(*) FROM records")[0][0],
            rows(db, "SELECT COUNT(*) FROM audit")[0][0])


def rewrite_tombstone(db: Path, seq: int, text: str) -> None:
    """Replace one tombstone and re-chain the audit from its purge row on, as a
    writer with direct access to the file could. The chain then verifies, so
    only the tombstone check itself can refuse what was written."""
    from canon.backends.sqlite import chain_hash

    con = sqlite3.connect(str(db))
    try:
        con.execute("UPDATE context_tombstones SET tombstone=? WHERE seq=?", (text, seq))
        con.execute("UPDATE audit SET sha256=? WHERE seq=?",
                    (hashlib.sha256(text.encode()).hexdigest(), seq))
        prev = con.execute("SELECT prev_hash FROM audit WHERE seq=?", (seq,)).fetchone()[0]
        for row_seq, key, sha, op in con.execute(
                "SELECT seq, key, sha256, op FROM audit WHERE seq>=? ORDER BY seq", (seq,)).fetchall():
            chain = chain_hash(prev, op, key, sha)
            con.execute("UPDATE audit SET prev_hash=?, chain_hash=? WHERE seq=?",
                        (prev, chain, row_seq))
            prev = chain
        con.commit()
    finally:
        con.close()
