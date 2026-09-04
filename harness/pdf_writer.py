"""pdf_writer.py -- a report as a PDF, written by hand from the stdlib.

The engine takes no runtime dependency, and a reporting library is not a good
enough reason to take the first one. A validation report is monospaced text on
a page, which is the one document a PDF writer can be small and honest about.

Two properties matter more than typography here:

Deterministic. No creation date, no producer string, no object id that depends
on anything but the content. The same report is the same bytes, so a PDF can be
hashed into a receipt and compared later.

Round-trippable. The answer that was checked rides along as an attached stream
under `/FlywheelAnswer` in the catalog. A reader ignores keys it does not know,
and `read_attachment` gets the JSON back without parsing a page.

The read side only claims PDFs this module wrote. Pulling values out of an
arbitrary PDF means guessing at a rendered layout, and a guess with a checker's
authority behind it is the failure this whole feature exists to prevent.
"""
from __future__ import annotations

import json
import re

# Letter, at 72 units to the inch, with a one-inch margin down to 54 points on
# the sides so a wide report line has somewhere to go.
PAGE_WIDTH, PAGE_HEIGHT = 612, 792
LEFT, TOP = 54, 738
FONT_SIZE, LEADING = 9, 12
# Courier is 0.6 em wide per glyph at every size, so the usable width is exact
# rather than estimated: (612 - 108) / (9 * 0.6) = 93.3.
WRAP = 93
LINES_PER_PAGE = 57


def wrap(text: str) -> list[str]:
    """Report lines, hard-wrapped, with the continuation indented under it.

    A wrapped reason that starts back at the margin reads as a new field, and
    the whole point of the report is which field is which.
    """
    out: list[str] = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.rstrip()
        if len(line) <= WRAP:
            out.append(line)
            continue
        indent = " " * (len(line) - len(line.lstrip()) + 2)
        while len(line) > WRAP:
            cut = line.rfind(" ", 0, WRAP)
            cut = cut if cut > len(indent) else WRAP
            out.append(line[:cut].rstrip())
            line = indent + line[cut:].lstrip()
        out.append(line)
    return out


def _latin1(text: str) -> bytes:
    """WinAnsi is a byte encoding, so anything outside it has to go.

    Substituting a question mark is visible. Dropping the character silently
    would let a report render as though it said something it did not.
    """
    return text.encode("cp1252", errors="replace")


def _escaped(line: str) -> bytes:
    body = _latin1(line)
    for old, new in ((b"\\", b"\\\\"), (b"(", b"\\("), (b")", b"\\)")):
        body = body.replace(old, new)
    return body


def _content(lines: list[str]) -> bytes:
    parts = [b"BT", f"/F1 {FONT_SIZE} Tf".encode("ascii"),
             f"{LEADING} TL".encode("ascii"),
             f"{LEFT} {TOP} Td".encode("ascii")]
    for line in lines:
        parts.append(b"(" + _escaped(line) + b") Tj T*")
    parts.append(b"ET")
    return b"\n".join(parts)


def _obj(number: int, body: bytes) -> bytes:
    return f"{number} 0 obj\n".encode("ascii") + body + b"\nendobj\n"


def _stream(body: bytes, extra: str = "") -> bytes:
    head = f"<< /Length {len(body)}{extra} >>".encode("ascii")
    return head + b"\nstream\n" + body + b"\nendstream"


def pdf_bytes(text: str, *, title: str = "", attachment: dict | None = None) -> bytes:
    """The report as a PDF page or pages, plus the answer it was about."""
    lines = wrap(f"{title}\n\n{text}" if title else text)
    pages = [lines[i:i + LINES_PER_PAGE]
             for i in range(0, max(len(lines), 1), LINES_PER_PAGE)] or [[""]]

    font_id = 3
    attach_id = 4 if attachment is not None else 0
    first_page = (attach_id or font_id) + 1
    page_ids = [first_page + 2 * i for i in range(len(pages))]

    catalog = "<< /Type /Catalog /Pages 2 0 R"
    if attach_id:
        catalog += f" /FlywheelAnswer {attach_id} 0 R"
    objects = {
        1: catalog.encode("ascii") + b" >>",
        2: (f"<< /Type /Pages /Kids [{' '.join(f'{i} 0 R' for i in page_ids)}] "
            f"/Count {len(page_ids)} >>").encode("ascii"),
        font_id: (b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier "
                  b"/Encoding /WinAnsiEncoding >>"),
    }
    if attach_id:
        # Sorted keys and a compact separator, so the same answer is the same
        # bytes on every machine that writes it.
        payload = json.dumps(attachment, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")
        objects[attach_id] = _stream(payload,
                                     " /Type /EmbeddedFile "
                                     "/Subtype /application#2Fjson")
    for page_id, page_lines in zip(page_ids, pages):
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox "
            f"[0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] /Contents {page_id + 1} 0 R "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>").encode("ascii")
        objects[page_id + 1] = _stream(_content(page_lines))

    out = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out += _obj(number, objects[number])
    start = len(out)
    count = max(objects) + 1
    out += f"xref\n0 {count}\n".encode("ascii")
    out += b"0000000000 65535 f \n"
    for number in range(1, count):
        # A gap in the numbering is a free entry, not a missing object. The
        # only gap here is the attachment slot when there is no attachment.
        if number in offsets:
            out += f"{offsets[number]:010d} 00000 n \n".encode("ascii")
        else:
            out += b"0000000000 65535 f \n"
    out += f"trailer\n<< /Size {count} /Root 1 0 R >>\nstartxref\n{start}\n".encode("ascii")
    out += b"%%EOF\n"
    return bytes(out)


def read_attachment(data: bytes) -> dict | None:
    """The answer a Flywheel PDF carries, or None if it carries none.

    None rather than an exception: a PDF from somewhere else is not a broken
    file, it is a file this module has nothing to say about.
    """
    ref = re.search(rb"/FlywheelAnswer\s+(\d+)\s+0\s+R", data)
    if not ref:
        return None
    number = int(ref.group(1))
    obj = re.search(rb"(?<![0-9])" + str(number).encode("ascii")
                    + rb"\s+0\s+obj\b(.*?)\bendobj", data, re.S)
    if not obj:
        return None
    body = re.search(rb"stream\r?\n(.*?)\r?\nendstream", obj.group(1), re.S)
    if not body:
        return None
    return json.loads(body.group(1).decode("utf-8"))
