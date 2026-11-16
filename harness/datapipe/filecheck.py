"""Stage 5, clean: file and licence checks, and the dated reversible change log."""
from __future__ import annotations

import dataclasses
import datetime as dt
import gzip
import hashlib
import json
import re
import zipfile
from pathlib import Path

from .access import SourceRecord, sha256_bytes, norm_text

STALE_DAYS = 365
ND_NC = re.compile(r"\b(ND|NC)\b|no[- ]?deriv|non[- ]?commercial", re.I)


def check_file_bytes(b: bytes, name: str, manifest_sha=None, declared_rows=None, width=None) -> list:
    """Truncation evidence. The hash needs a manifest; the structure tests work without one and can miss a clean line-boundary cut."""
    out = []
    if not b:
        return ["empty file"]
    if manifest_sha and sha256_bytes(b) != manifest_sha:
        out.append("hash differs from manifest")
    low = name.lower()
    if low.endswith(".zip"):
        try:
            import io
            if zipfile.ZipFile(io.BytesIO(b)).testzip() is not None:
                out.append("zip member fails its CRC")
        except zipfile.BadZipFile:
            out.append("zip directory absent")
    elif low.endswith(".gz"):
        try:
            gzip.decompress(b)
        except (OSError, EOFError):
            out.append("gzip stream ends early")
    elif low.endswith((".sqlite", ".db")):
        if b[:16] == b"SQLite format 3\x00" and len(b) >= 32:
            page = int.from_bytes(b[16:18], "big") or 65536
            count = int.from_bytes(b[28:32], "big")
            if count and page * count != len(b):
                out.append("sqlite length differs from its header")
    else:
        if not b.endswith((b"\n", b"\r")):
            out.append("last line has no terminator")
        lines = [ln for ln in b.decode("utf8", "replace").splitlines() if ln.strip()]
        if width and lines and len(lines[-1].split(",")) != width:
            out.append(f"last row has {len(lines[-1].split(','))} cells, table has {width}")
        if declared_rows is not None and len(lines) != declared_rows:
            out.append(f"{len(lines)} lines, {declared_rows} declared")
    return out


def baseline_file(b: bytes) -> list:
    """The simple baseline: nonempty, and it decodes."""
    if not b:
        return ["empty"]
    try:
        b.decode("utf8")
    except UnicodeDecodeError:
        pass
    return []


def check_licence(rec: SourceRecord, root, today="2026-10-31") -> list:
    """Evidence for the licence claim: the gate's own tests, age of the reading, and whether the claim agrees with the quote."""
    out = list(rec.problems(root))
    if rec.basis == "read":
        if rec.terms_read_at:
            age = (dt.date.fromisoformat(today) - dt.date.fromisoformat(rec.terms_read_at[:10])).days
            if age > STALE_DAYS:
                out.append(f"terms read {age} days ago")
        if rec.redistribution == "yes" and ND_NC.search(rec.licence):
            out.append("licence limits derivatives or commerce, record says redistribution yes")
        if rec.redistribution == "yes" and not licence_in_quote(rec.licence, rec.licence_quote):
            out.append("licence field does not agree with the quote")
        if re.search(r"\bmemory\b|as i recall", rec.notes, re.I):
            out.append("notes say memory")
    return out


def licence_in_quote(licence: str, quote: str) -> bool:
    q = norm_text(quote).replace("-", " ")
    l = licence.lower()
    if l.startswith("cc0"):
        return "cc0" in q or "publicdomain/zero" in q or "public domain" in q
    m = re.match(r"cc-by(-sa)?(-nd)?(-nc)?-(\d)\.(\d)", l)
    if m:
        ver_ok = f"{m.group(4)}.{m.group(5)}" in q or f"{m.group(4)}.0" in q
        named = "creative commons" in q or "cc by" in q
        sa_ok = (m.group(1) is not None) == ("share" in q or "by sa" in q)
        return ver_ok and named and sa_ok
    return True


def baseline_licence(rec: SourceRecord) -> list:
    """The simple baseline: the licence field is filled in."""
    return [] if rec.licence and rec.licence != "unknown" else ["licence empty"]


@dataclasses.dataclass
class Change:
    date: str
    table: str
    row: int
    col: int
    was: str
    now: str
    why: str
    check: str


class ChangeLog:
    """Every edit is a dated row that can be undone. Deletion is absent on purpose; a bad row gets a flag and stays."""

    def __init__(self, path=None):
        self.path, self.rows = Path(path) if path else None, []

    def apply(self, table, row, col, now, why, check, date="2026-10-31") -> Change:
        was = table.rows[row][col]
        table.rows[row][col] = now
        c = Change(date, table.name, row, col, was, now, why, check)
        self.rows.append(c)
        if self.path:
            with open(self.path, "a", encoding="utf8") as f:
                f.write(json.dumps(dataclasses.asdict(c), ensure_ascii=False) + "\n")
        return c

    def revert(self, table) -> None:
        for c in reversed(self.rows):
            if c.table == table.name:
                if table.rows[c.row][c.col] != c.now:
                    raise ValueError(f"row {c.row} changed outside the log")
                table.rows[c.row][c.col] = c.was


def table_hash(table) -> str:
    return hashlib.sha256(json.dumps(table.rows, ensure_ascii=False).encode()).hexdigest()
