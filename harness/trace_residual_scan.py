"""The residual scan: is deleted text still in the files the tools control?
(7.10, EN-C9, I4)

Needles are every 16-byte window of each deleted text in UTF-8, UTF-16LE,
JSON-escaped (ASCII and not), base64 at three alignments, and the NFC and NFD
normalizations. A file is checked at every offset that is a multiple of 16,
so any copy of 31 bytes or more of a long text is found in any of those forms,
including one split across SQLite overflow pages. Texts under 256 bytes are
searched whole in every form; texts under 16 bytes get structural checks
only, and the count says so. Windows that also occur in rows the deletion
keeps are subtracted, so kept text is not reported as residue.

It reports hit counts per file label and never surrounding text. It shows
that these byte patterns are absent from these files now; it does not look at
freed clusters, NTFS metadata, backups, shadow copies, the pagefile or any
transformation it does not search for. Encrypted custody files are ciphertext,
so a pattern can never be found in them: they are counted as not searched, and
a zero count says nothing about them. A compressed file it cannot open (a
.zst with no zstd module, or one over the zstd bounds) is counted the same way.
"""
from __future__ import annotations

import base64
import gzip
import json
from pathlib import Path
import unicodedata
import zipfile

WIDTH = 16
SHORT_MAX = 256
MAX_READ = 512 * 1024 * 1024


def forms(text: str) -> list[bytes]:
    out = []
    for variant in {text, unicodedata.normalize("NFC", text), unicodedata.normalize("NFD", text)}:
        raw = variant.encode("utf-8")
        out += [raw, variant.encode("utf-16-le"), json.dumps(variant)[1:-1].encode("ascii"),
                json.dumps(variant, ensure_ascii=False)[1:-1].encode("utf-8")]
        for shift in range(3):
            encoded = base64.b64encode(b"\0" * shift + raw)
            out.append(encoded[4:-4] if len(encoded) > 8 else b"")
    return [f for f in out if f]


def _windows(blob: bytes) -> set[bytes]:
    return {blob[i:i + WIDTH] for i in range(0, max(len(blob) - WIDTH + 1, 0))}


class Needles:
    def __init__(self) -> None:
        self.windows: set[bytes] = set()
        self.shorts: list[bytes] = []
        self.structural_only = 0
        self.subtracted = 0

    @classmethod
    def build(cls, texts, live=()) -> "Needles":
        needles = cls()
        for text in texts:
            size = len(text.encode("utf-8"))
            if size < WIDTH:
                needles.structural_only += 1
            elif size < SHORT_MAX:
                needles.shorts.extend(f for f in set(forms(text)) if len(f) >= WIDTH)
            else:
                for form in forms(text):
                    needles.windows |= _windows(form)
        kept = [f for text in live for f in forms(text)]
        kept_windows = set().union(*(_windows(f) for f in kept)) if kept else set()
        before = len(needles.windows)
        needles.windows -= kept_windows
        needles.subtracted = before - len(needles.windows)
        shorts = [s for s in needles.shorts if not any(s in f for f in kept)]
        needles.subtracted += len(needles.shorts) - len(shorts)
        needles.shorts = shorts
        return needles


def scan_bytes(data: bytes, needles: Needles) -> int:
    hits = 0
    windows = needles.windows
    if windows:
        for index in range(0, len(data) - WIDTH + 1, WIDTH):
            if data[index:index + WIDTH] in windows:
                hits += 1
    for short in needles.shorts:
        hits += data.count(short)
    return hits


class Unopened(Exception):
    pass


def _zst(data: bytes) -> bytes:
    from .trace_zstd import InputBound, Stream
    pieces: list[bytes] = []
    try:
        stream = Stream(pieces.append, max_output=MAX_READ)
        stream.feed(data)
    except InputBound:
        raise Unopened() from None
    return b"".join(pieces)


def _payloads(path: Path, data: bytes):
    yield data
    name = path.name.lower()
    try:
        if name.endswith(".gz"):
            yield gzip.decompress(data)[:MAX_READ]
        elif name.endswith(".zip"):
            with zipfile.ZipFile(path) as archive:
                for member in archive.infolist()[:10_000]:
                    yield archive.read(member)[:MAX_READ]
        elif name.endswith(".zst"):
            yield _zst(data)
    except (OSError, ValueError, EOFError, zipfile.BadZipFile):
        raise Unopened() from None


def scan_paths(paths, needles: Needles, *, labels=None) -> dict:
    from .trace_enc import is_encrypted
    labels = labels or {}
    per_file, total, unsearched = {}, 0, {"encrypted": 0, "compressed": 0}
    for path in paths:
        path = Path(path)
        if not path.is_file():
            continue
        data = path.read_bytes()[:MAX_READ]
        if is_encrypted(data):
            unsearched["encrypted"] += 1
            continue
        hits = 0
        try:
            for payload in _payloads(path, data):
                hits += scan_bytes(payload, needles)
        except Unopened:
            unsearched["compressed"] += 1
        if hits:
            per_file[labels.get(path, path.name)] = hits
            total += hits
    return {"per_file": per_file, "total": total, "unsearched": unsearched,
            "structural_only": needles.structural_only}
