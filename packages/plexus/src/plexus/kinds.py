"""kinds.py: what an item is, read from the item itself.

The vocabulary is fixed (KINDS). `detect` reads a path's leading bytes and its
extension, a URL's shape, or a short literal's form, and returns every kind
that fits, each with the evidence that put it there. It never opens a network
connection and never reads more than HEAD_BYTES of a file. When nothing fits,
the answer says so: `unknown` is True and `kinds` holds only what is certain
(a readable file is always `file`).
"""
from __future__ import annotations

import json
import os
import re

SCHEMA = "plexus.kinds/1"
HEAD_BYTES = 64 * 1024

KINDS = (
    "file", "web", "html", "post", "feed", "paper", "pdf", "archive", "folder",
    "image", "vector", "video", "audio", "voice", "music", "series", "table",
    "spectrum", "field", "colour", "geometry", "model3d", "lens", "circuit",
    "material", "code", "repo", "prose", "symbols", "claim", "memory", "formula",
    "law", "seed", "screen",
)

_EXT = {
    "image": {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"},
    "vector": {".svg"},
    "video": {".mp4", ".webm", ".mkv", ".mov", ".avi", ".m4v"},
    "audio": {".wav", ".flac", ".mp3", ".ogg", ".opus", ".m4a", ".aac"},
    "archive": {".zip", ".7z", ".tar", ".gz", ".tgz", ".docx", ".xlsx", ".pptx"},
    "pdf": {".pdf"},
    "html": {".html", ".htm"},
    "prose": {".md", ".txt", ".rst"},
    "table": {".csv", ".tsv", ".sqlite", ".db"},
    "model3d": {".obj", ".gltf", ".glb", ".stl", ".vox", ".ply"},
    "code": {".py", ".js", ".mjs", ".cjs", ".ts", ".rs", ".bld", ".c", ".h", ".cpp",
             ".hpp", ".go", ".java", ".rb", ".hlsl", ".glsl", ".sh", ".ps1", ".lua"},
}

# Kinds that describe content, not form: no byte signature or URL shape shows
# them, so `detect` never returns them and a caller adds them (fanout --kind).
CALLER_ONLY = ("voice", "music", "field", "geometry", "material", "symbols", "memory",
               "law", "screen")

_TEXT_KINDS ={"prose", "table", "code", "html", "vector", "model3d"}

# (offset, magic bytes, kinds)
_MAGIC = [
    (0, b"\x89PNG\r\n\x1a\n", ("image",)),
    (0, b"\xff\xd8\xff", ("image",)),
    (0, b"GIF87a", ("image",)),
    (0, b"GIF89a", ("image",)),
    (0, b"BM", None),                       # too short to trust alone; see _magic
    (0, b"%PDF", ("pdf",)),
    (0, b"PK\x03\x04", ("archive",)),
    (0, b"7z\xbc\xaf\x27\x1c", ("archive",)),
    (0, b"\x1f\x8b", ("archive",)),
    (257, b"ustar", ("archive",)),
    (0, b"fLaC", ("audio",)),
    (0, b"ID3", ("audio",)),
    (0, b"OggS", ("audio",)),
    (0, b"\x1aE\xdf\xa3", ("video", "audio")),
    (0, b"glTF", ("model3d",)),
    (0, b"VOX ", ("model3d",)),
    (0, b"SQLite format 3\x00", ("table",)),
]

_URL = re.compile(r"^https?://[^\s]+$", re.I)
_HEX = re.compile(r"^#?(?:[0-9a-f]{3}|[0-9a-f]{6}|[0-9a-f]{8})$", re.I)
_RGB = re.compile(r"^(?:rgb|hsl|lab|oklab|oklch)a?\(\s*[-0-9.%]+(?:[ ,/]+[-0-9.%]+){2,3}\s*\)$", re.I)
_ARXIV = re.compile(r"^(?:arxiv:)?\d{4}\.\d{4,5}(?:v\d+)?$", re.I)
_DOI = re.compile(r"^(?:doi:)?10\.\d{4,9}/\S+$", re.I)
_FORMULA = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*/\d+$")
_SEED = re.compile(r"^-?\d{1,20}$")
_POST_HOSTS = ("reddit.com", "x.com", "twitter.com", "bsky.app", "mastodon.")
_PAPER_HOSTS = ("arxiv.org", "doi.org", "openreview.net", "biorxiv.org", "medrxiv.org")


class _Found:
    def __init__(self):
        self.kinds: dict[str, str] = {}

    def add(self, kind: str, why: str) -> None:
        if kind not in KINDS:
            raise ValueError(f"not a kind: {kind}")
        self.kinds.setdefault(kind, why)


def _magic(head: bytes, f: _Found) -> None:
    for off, sig, kinds in _MAGIC:
        if kinds and head[off:off + len(sig)] == sig:
            for k in kinds:
                f.add(k, f"magic {sig[:8]!r} at {off}")
    if head[:4] == b"RIFF" and len(head) >= 12:
        sub = head[8:12]
        if sub == b"WAVE":
            f.add("audio", "magic RIFF/WAVE")
        elif sub == b"WEBP":
            f.add("image", "magic RIFF/WEBP")
        elif sub == b"AVI ":
            f.add("video", "magic RIFF/AVI")
            f.add("audio", "video container (KINDS: video carries audio)")
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in (b"M4A ", b"M4B "):
            f.add("audio", f"ftyp brand {brand!r}")
        else:
            f.add("video", f"ftyp brand {brand!r}")
            f.add("audio", "video container (KINDS: video carries audio)")
    if head[:2] == b"BM" and len(head) > 26 and head[14] in (12, 40, 56, 108, 124):
        f.add("image", "magic BM with a DIB header")
    if len(head) >= 3 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0 and head[1] & 0x06:
        f.add("audio", "MPEG audio frame sync")


def _text(head: bytes) -> "str | None":
    if b"\x00" in head[:4096]:
        return None
    try:
        return head.decode("utf-8")
    except UnicodeDecodeError as e:
        if e.start >= len(head) - 4:          # a multi-byte character cut at the end
            return head[:e.start].decode("utf-8", "ignore")
        return None


def _numeric_columns(lines: list, sep: str) -> "tuple[int, list]":
    rows = [ln.split(sep) for ln in lines if ln.strip()]
    if len(rows) < 3:
        return 0, []
    header = rows[0]
    body = rows[1:]
    width = len(header)
    numeric = []
    for c in range(width):
        vals = [r[c].strip() for r in body if len(r) > c]
        try:
            [float(v) for v in vals if v]
            numeric.append(c)
        except ValueError:
            pass
    return width, [header[c].strip().lower() for c in numeric]


def _sniff_text(text: str, ext: str, f: _Found) -> None:
    low = text.lstrip()[:2048].lower()
    if low.startswith("<?xml") or low.startswith("<"):
        if "<svg" in low:
            f.add("vector", "text holds <svg")
        if "<rss" in low or ("<feed" in low and "atom" in low):
            f.add("feed", "text holds <rss> or an Atom <feed>")
        if "<html" in low or "<!doctype html" in low:
            f.add("html", "text holds <html>")
    if ext in (".csv", ".tsv") or (ext == ".txt" and "\t" in text[:500]):
        sep = "\t" if (ext == ".tsv" or text.count("\t") > text.count(",")) else ","
        f.add("table", f"delimited text ({'tab' if sep == chr(9) else 'comma'})")
        width, numeric = _numeric_columns(text.splitlines()[:200], sep)
        if numeric:
            f.add("series", f"{len(numeric)} numeric column(s)")
        words = set(re.split(r"[^a-z]+", " ".join(numeric)))
        if len(numeric) >= 2 and words & {"nm", "wavelength", "hz", "freq", "frequency", "lambda"}:
            f.add("spectrum", "numeric column named for wavelength or frequency")
    if ext == ".json" or low.startswith(("{", "[")):
        _sniff_json(text, f)
    if ext in (".md", ".txt", ".rst") and "prose" not in f.kinds and "table" not in f.kinds:
        f.add("prose", f"extension {ext}")


def _sniff_json(text: str, f: _Found) -> None:
    try:
        data = json.loads(text)
    except (ValueError, RecursionError):
        return                                   # truncated or not JSON: leave it
    if isinstance(data, list) and data and all(isinstance(r, dict) for r in data[:50]):
        f.add("table", "JSON list of records")
        return
    if not isinstance(data, dict):
        return
    keys = {k.lower() for k in data}
    if "claims" in keys or "thesis" in keys:
        f.add("claim", "JSON with claims or thesis")
    if "surfaces" in keys and ("glass" in text or "radius" in text):
        f.add("lens", "JSON with surfaces and radii or glasses")
    if {"nets", "components"} & keys or "netlist" in keys:
        f.add("circuit", "JSON with nets or components")
    if {"author", "date"} <= keys and ({"text", "body", "replies", "url"} & keys):
        f.add("post", "JSON with author, date and text")


def _sidecar_post(path: str, f: _Found) -> None:
    stem, ext = os.path.splitext(path)
    for side in (".md", ".json"):
        cand = stem + side
        if cand != path and os.path.isfile(cand):
            f.add("post", f"sidecar {os.path.basename(cand)} beside the item")
            return


def _detect_url(url: str, f: _Found) -> None:
    f.add("web", "http(s) URL")
    host = re.sub(r"^https?://", "", url, flags=re.I).split("/")[0].lower()
    path = url.split("?")[0].split("#")[0]
    ext = os.path.splitext(path)[1].lower()
    if any(h in host for h in _POST_HOSTS) or ("youtube.com" in host and "lc=" in url):
        f.add("post", f"social host {host}")
    if any(host.endswith(h) for h in _PAPER_HOSTS):
        f.add("paper", f"paper host {host}")
    if ext in (".rss", ".atom") or re.search(r"/(feed|rss)(\.xml)?/?$", path, re.I):
        f.add("feed", "feed-shaped URL path")
    for kind, exts in _EXT.items():
        if ext in exts:
            f.add(kind, f"URL path extension {ext}")


def _detect_literal(text: str, f: _Found) -> None:
    s = text.strip()
    if _HEX.match(s) and (s.startswith("#") or re.search(r"[a-f]", s, re.I)):
        f.add("colour", "hex colour")
    elif _RGB.match(s):
        f.add("colour", "colour function")
    elif _ARXIV.match(s) or _DOI.match(s):
        f.add("paper", "arXiv id or DOI")
    elif _FORMULA.match(s):
        f.add("formula", "formula registry id")
    elif _SEED.match(s):
        f.add("seed", "integer")
    elif s.startswith(("{", "[")):
        _sniff_json(s, f)
    elif len(s.split()) >= 3:
        f.add("prose", "free text of three or more words")


def _looks_like_path(s: str) -> bool:
    return bool(re.match(r"^(?:[a-zA-Z]:[\\/]|[\\/]|\.{1,2}[\\/]|~[\\/])", s)) or (
        ("/" in s or "\\" in s) and " " not in s.strip() and bool(os.path.splitext(s)[1]))


def detect(item: str) -> dict:
    """Kinds of one item (a path, a URL or a short literal). JSON-ready."""
    f = _Found()
    item = "" if item is None else str(item)
    how = "literal"
    reason = ""
    if not item.strip():
        reason = "empty item"
    elif _URL.match(item.strip()):
        how = "url"
        _detect_url(item.strip(), f)
    elif os.path.isdir(item):
        how = "folder"
        f.add("folder", "a directory")
        if os.path.exists(os.path.join(item, ".git")):
            f.add("repo", "directory holds .git")
    elif os.path.isfile(item):
        how = "file"
        f.add("file", "a readable file")
        ext = os.path.splitext(item)[1].lower()
        with open(item, "rb") as fh:
            head = fh.read(HEAD_BYTES)
        _magic(head, f)
        text = _text(head) if len(f.kinds) == 1 else None
        for kind, exts in _EXT.items():
            # An extension confirms what the bytes say. On its own it counts
            # only for kinds stored as text (a .png full of text is not a picture).
            if ext in exts and (kind in f.kinds or (text is not None and kind in _TEXT_KINDS)):
                f.add(kind, f"extension {ext}")
        if ext in (".stl", ".ply") and text is None and len(f.kinds) == 1 and len(head) >= 84:
            f.add("model3d", f"binary {ext}")
        if text is not None:
            _sniff_text(text, ext, f)
        if ext == ".pdf" and re.search(r"^\d{4}\.\d{4,5}", os.path.basename(item)):
            f.add("paper", "PDF named as an arXiv id")
        _sidecar_post(item, f)
    elif _looks_like_path(item):
        how = "path"
        reason = "no such path"
    else:
        _detect_literal(item, f)
    kinds = [k for k in KINDS if k in f.kinds]
    informative = [k for k in kinds if k != "file"]
    unknown = not informative
    if unknown and not reason:
        reason = "no kind beyond file fits" if kinds else "no kind fits"
    return {"schema": SCHEMA, "item": item, "read_as": how, "kinds": kinds,
            "evidence": {k: f.kinds[k] for k in kinds}, "unknown": unknown,
            "reason": reason if unknown else ""}
