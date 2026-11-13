"""Bounded, read-only window reads over local harness transcripts.

A Claude Code transcript or a Codex rollout can be gigabytes long and is
appended to while the session runs. The observers never read a whole file.
They read a head window and a tail window, record the byte offsets and the
SHA-256 of exactly the bytes they read, and drop the partial line at the
front of the tail. Nothing here follows a symbolic link, opens a device, or
writes. This reader admits the operator's own local files; it is not an
upload boundary, so it does not replace private_artifact_fs for foreign
captures.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat

DEFAULT_HEAD_BYTES = 262_144
DEFAULT_TAIL_BYTES = 4_194_304
MAX_WINDOW_BYTES = 67_108_864
MAX_LINE_BYTES = 8_388_608


class SourceRejected(ValueError):
    """The source path is not a regular, link-free file we may read."""


LINK_TAGS = tuple(tag for tag in (getattr(stat, "IO_REPARSE_TAG_SYMLINK", None),
                                  getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", None))
                  if tag is not None)


def is_link(path: Path) -> bool:
    """True for a symbolic link and for a Windows junction.

    Path.is_symlink() reports False for a directory junction, so a junction
    planted in a transcript tree would be walked as an ordinary directory and
    could redirect the reader anywhere on the machine. Only name-surrogate
    reparse tags count here, so a cloud-storage placeholder stays an ordinary
    file. A path that cannot be stat'd is treated as a link, because refusing
    to read it is the safe answer.
    """
    try:
        if path.is_symlink():
            return True
        st = path.lstat()
    except OSError:
        return True
    return getattr(st, "st_reparse_tag", 0) in LINK_TAGS


def _utc(ts: float) -> str:
    """A fixed-width UTC stamp. Microseconds are always written, so two stamps
    compare as strings in the same order as the instants they name."""
    return (datetime.fromtimestamp(ts, timezone.utc)
            .isoformat(timespec="microseconds").replace("+00:00", "Z"))


def _window(fh, offset: int, length: int, *, drop_partial_first: bool) -> dict:
    """Read one window. A tail window that starts mid-line drops the partial line;
    one that starts right after a newline keeps every byte."""
    on_boundary = True
    if drop_partial_first and offset > 0:
        fh.seek(offset - 1)
        on_boundary = fh.read(1) == b"\n"
    fh.seek(offset)
    data = fh.read(length)
    dropped = 0
    if drop_partial_first and offset > 0 and not on_boundary:
        cut = data.find(b"\n")
        dropped = len(data) if cut < 0 else cut + 1
        data = data[dropped:]
        offset += dropped
    return {"offset": offset, "length": len(data), "dropped_partial_prefix_bytes": dropped,
            "sha256": hashlib.sha256(data).hexdigest(), "_bytes": data}


def read_windows(path: str | os.PathLike[str], *, head_bytes: int = DEFAULT_HEAD_BYTES,
                 tail_bytes: int = DEFAULT_TAIL_BYTES) -> dict:
    """Read a head window and a tail window with provenance.

    Returns {"source": {...}, "head": {...}, "tail": {...}}. Each window carries
    offset, length, sha256 and the raw bytes under the private key "_bytes",
    which callers strip before emitting. When the file fits in one window the
    tail is the head and "overlap" is True.
    """
    for name, value in (("head_bytes", head_bytes), ("tail_bytes", tail_bytes)):
        if type(value) is not int or value <= 0 or value > MAX_WINDOW_BYTES:
            raise SourceRejected(f"{name} out of range")
    p = Path(path)
    if is_link(p):
        raise SourceRejected("symbolic link refused")
    try:
        st = p.lstat()
    except OSError as exc:
        raise SourceRejected("source unreadable") from exc
    if not stat.S_ISREG(st.st_mode):
        raise SourceRejected("not a regular file")
    with p.open("rb") as fh:
        live = os.fstat(fh.fileno())
        if not stat.S_ISREG(live.st_mode):
            raise SourceRejected("not a regular file")
        size = live.st_size
        head = _window(fh, 0, min(head_bytes, size), drop_partial_first=False)
        tail_is_head = size <= head_bytes
        if tail_is_head:
            tail = dict(head)
        else:
            tail = _window(fh, max(size - tail_bytes, 0), tail_bytes, drop_partial_first=True)
    overlap = tail_is_head or tail["offset"] < head["offset"] + head["length"]
    covered = tail["offset"] == 0 and tail["length"] == size
    source = {"path": str(p), "size_bytes": size, "mtime_utc": _utc(live.st_mtime),
              "windows_overlap": overlap, "tail_window_is_head_window": tail_is_head,
              "whole_file_read": overlap or covered}
    return {"source": source, "head": head, "tail": tail}


def public_window(window: dict) -> dict:
    """The window record without its bytes."""
    return {k: v for k, v in window.items() if k != "_bytes"}


def iter_jsonl(data: bytes) -> tuple[list[tuple[int, dict]], dict]:
    """Parse JSON object lines from a window. Returns (records, parse_report).

    Lines that are not JSON objects are counted, never raised: a live file can
    end mid-write. Offsets are relative to the window start.
    """
    records: list[tuple[int, dict]] = []
    report = {"lines": 0, "objects": 0, "unparsed_lines": 0, "oversize_lines": 0,
              "trailing_partial_line": False}
    offset = 0
    for raw in data.split(b"\n"):
        if raw == b"" and offset >= len(data):
            break
        report["lines"] += 1
        if len(raw) > MAX_LINE_BYTES:
            report["oversize_lines"] += 1
        else:
            try:
                value = json.loads(raw)
            except ValueError:
                value = None
            if type(value) is dict:
                records.append((offset, value))
                report["objects"] += 1
            else:
                report["unparsed_lines"] += 1
        offset += len(raw) + 1
    if data and not data.endswith(b"\n"):
        report["trailing_partial_line"] = True
    return records, report


def text_digest(value: object) -> dict | None:
    """Content-minimized reference to a string: length and hash, never text.

    A JSON source may hand back a string holding a lone surrogate, which plain
    UTF-8 refuses to encode. Such a string is hashed through surrogatepass and
    marked, so one malformed field cannot abort an observation.
    """
    if type(value) is not str:
        return None
    try:
        return {"chars": len(value), "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest()}
    except UnicodeEncodeError:
        raw = value.encode("utf-8", errors="surrogatepass")
        return {"chars": len(value), "sha256": hashlib.sha256(raw).hexdigest(),
                "utf8_encodable": False}


def age_seconds(mtime_utc: object, now_utc: object) -> float | None:
    """Seconds between two ISO-8601 stamps, or None when either is not one."""
    try:
        m = datetime.fromisoformat(mtime_utc.replace("Z", "+00:00"))
        n = datetime.fromisoformat(now_utc.replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        return None
    if m.tzinfo is None or n.tzinfo is None:
        return None
    return (n - m).total_seconds()


__all__ = ["DEFAULT_HEAD_BYTES", "DEFAULT_TAIL_BYTES", "MAX_WINDOW_BYTES", "SourceRejected",
           "age_seconds", "is_link", "iter_jsonl", "public_window", "read_windows",
           "text_digest"]
