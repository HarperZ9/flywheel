"""Binary metadata checks for check_publish_metadata.py: images, PDFs, Office files.

Each check returns a list of (category, detail) pairs. Each fixer returns new
bytes, or None when it cannot fix the file safely. Stdlib only.

What each one keeps on purpose:
- PNG: every chunk except tEXt, zTXt, iTXt, eXIf and tIME. iCCP, gAMA, cHRM,
  sRGB and the image data stay, so colour is unchanged.
- JPEG: every segment except APP1 (Exif, XMP) and APP13 (IPTC). APP2 carries the
  ICC profile and stays.
- PDF: /Author and /Creator strings and the XMP packet are blanked with spaces
  of the same length, so xref offsets and stream lengths stay valid. Metadata
  inside a compressed stream is reported and left for a rebuild.
- OOXML (docx, xlsx, pptx): dc:creator and cp:lastModifiedBy are emptied and
  docProps/custom.xml is dropped with its content-type and relationship entries.
"""
from __future__ import annotations

import io
import re
import zipfile
import zlib

PNG_SIG = b"\x89PNG\r\n\x1a\n"
PNG_DROP = {b"tEXt", b"zTXt", b"iTXt", b"eXIf", b"tIME"}
IMAGE_EXT = {".png", ".jpg", ".jpeg"}
PDF_EXT = {".pdf"}
OOXML_EXT = {".docx", ".xlsx", ".pptx", ".docm", ".xlsm", ".pptm"}


# ---------- PNG ----------

def _png_chunks(data: bytes):
    pos = len(PNG_SIG)
    while pos + 8 <= len(data):
        length = int.from_bytes(data[pos:pos + 4], "big")
        kind = data[pos + 4:pos + 8]
        end = pos + 12 + length
        yield kind, pos, end
        pos = end
        if kind == b"IEND":
            break


def check_png(data: bytes):
    out = []
    for kind, start, _end in _png_chunks(data):
        if kind in PNG_DROP:
            what = "EXIF" if kind == b"eXIf" else "text" if kind != b"tIME" else "timestamp"
            out.append(("image-metadata", f"PNG {kind.decode()} chunk ({what}) at byte {start}"))
    return out


def fix_png(data: bytes):
    parts = [PNG_SIG]
    tail = len(PNG_SIG)
    for kind, start, end in _png_chunks(data):
        if kind not in PNG_DROP:
            parts.append(data[start:end])
        tail = end
    parts.append(data[tail:])
    return b"".join(parts)


# ---------- JPEG ----------

def _jpeg_segments(data: bytes):
    """Yield (marker, start, end) for header segments up to start of scan."""
    pos = 2
    while pos + 4 <= len(data) and data[pos] == 0xFF:
        marker = data[pos + 1]
        if marker == 0xFF:          # fill byte
            pos += 1
            continue
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            yield marker, pos, pos + 2
            pos += 2
            continue
        length = int.from_bytes(data[pos + 2:pos + 4], "big")
        yield marker, pos, pos + 2 + length
        if marker == 0xDA:          # start of scan: the rest is image data
            return
        pos += 2 + length


def _jpeg_meta_kind(data: bytes, marker: int, start: int):
    body = data[start + 4:start + 40]
    if marker == 0xE1:
        if body.startswith(b"Exif"):
            return "EXIF"
        if body.startswith(b"http://ns.adobe.com/xap") or b"xmp" in body.lower():
            return "XMP"
        return "APP1"
    if marker == 0xED:
        return "IPTC"
    return None


def check_jpeg(data: bytes):
    out = []
    for marker, start, _end in _jpeg_segments(data):
        kind = _jpeg_meta_kind(data, marker, start)
        if kind:
            out.append(("image-metadata", f"JPEG {kind} segment at byte {start}"))
    return out


def fix_jpeg(data: bytes):
    parts = [data[:2]]
    tail = 2
    for marker, start, end in _jpeg_segments(data):
        if not _jpeg_meta_kind(data, marker, start):
            parts.append(data[start:end])
        tail = end
    parts.append(data[tail:])
    return b"".join(parts)


# ---------- PDF ----------

_PDF_STR = rb"(\((?:\\.|[^\\)])*\)|<[0-9A-Fa-f\s]*>)"
_PDF_KEYS = re.compile(rb"/(Author|Creator)\s*" + _PDF_STR)
_XMP = re.compile(rb"<x:xmpmeta.*?</x:xmpmeta>", re.S)
_STREAM = re.compile(rb"stream\r?\n(.*?)endstream", re.S)


def _blank(value: bytes) -> bool:
    inner = value[1:-1].strip()
    return inner in (b"", b"FEFF", b"feff")


def check_pdf(data: bytes):
    out = []
    for m in _PDF_KEYS.finditer(data):
        if not _blank(m.group(2)):
            out.append(("pdf-metadata", f"/{m.group(1).decode()} is set"))
    if _XMP.search(data):
        out.append(("pdf-metadata", "XMP metadata packet present"))
    for s in _STREAM.finditer(data):
        try:
            inner = zlib.decompress(s.group(1))
        except zlib.error:
            continue
        hits = [m.group(1).decode() for m in _PDF_KEYS.finditer(inner) if not _blank(m.group(2))]
        if hits or _XMP.search(inner):
            what = ", ".join(sorted(set(hits)) + (["XMP"] if _XMP.search(inner) else []))
            out.append(("pdf-metadata", f"compressed stream carries {what} (rebuild needed)"))
    return out


def _blank_value(m: re.Match) -> bytes:
    value = m.group(2)
    head = m.group(0)[:m.start(2) - m.start(0)]
    return head + value[:1] + b" " * (len(value) - 2) + value[-1:]


def fix_pdf(data: bytes):
    data = _PDF_KEYS.sub(_blank_value, data)
    data = _XMP.sub(lambda m: b" " * len(m.group(0)), data)
    return data


# ---------- OOXML ----------

_CORE_FIELDS = re.compile(
    rb"(<(dc:creator|cp:lastModifiedBy)\b[^>]*>)([^<]*)(</\2>)")


def check_ooxml(data: bytes):
    out = []
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return [("office-metadata", "unreadable zip container")]
    names = set(z.namelist())
    if "docProps/core.xml" in names:
        for m in _CORE_FIELDS.finditer(z.read("docProps/core.xml")):
            if m.group(3).strip():
                out.append(("office-metadata", f"core.xml {m.group(2).decode()} is set"))
    if "docProps/custom.xml" in names:
        out.append(("office-metadata", "docProps/custom.xml present"))
    return out


def fix_ooxml(data: bytes):
    src = zipfile.ZipFile(io.BytesIO(data))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as dst:
        for info in src.infolist():
            if info.filename == "docProps/custom.xml":
                continue
            body = src.read(info.filename)
            if info.filename == "docProps/core.xml":
                body = _CORE_FIELDS.sub(lambda m: m.group(1) + m.group(4), body)
            elif info.filename == "[Content_Types].xml":
                body = re.sub(rb'<Override[^>]*PartName="/docProps/custom\.xml"[^>]*/>', b"", body)
            elif info.filename == "_rels/.rels":
                body = re.sub(rb'<Relationship[^>]*Target="/?docProps/custom\.xml"[^>]*/>', b"", body)
            dst.writestr(info, body, compress_type=info.compress_type)
    return buf.getvalue()


# ---------- dispatch ----------

def check_binary(suffix: str, data: bytes):
    if suffix == ".png" and data.startswith(PNG_SIG):
        return check_png(data)
    if suffix in (".jpg", ".jpeg") and data.startswith(b"\xff\xd8"):
        return check_jpeg(data)
    if suffix in PDF_EXT and data.startswith(b"%PDF"):
        return check_pdf(data)
    if suffix in OOXML_EXT:
        return check_ooxml(data)
    return []


def fix_binary(suffix: str, data: bytes):
    if suffix == ".png":
        return fix_png(data)
    if suffix in (".jpg", ".jpeg"):
        return fix_jpeg(data)
    if suffix in PDF_EXT:
        return fix_pdf(data)
    if suffix in OOXML_EXT:
        return fix_ooxml(data)
    return None


BINARY_EXT = IMAGE_EXT | PDF_EXT | OOXML_EXT
