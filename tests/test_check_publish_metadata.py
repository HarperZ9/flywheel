"""check_publish_metadata: binary metadata is found, fixed, and the colour data kept.

Leak strings are built at run time so this file does not itself carry them.
"""
import importlib.util
import io
import struct
import sys
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
_spec = importlib.util.spec_from_file_location(
    "check_publish_metadata", ROOT / "scripts" / "check_publish_metadata.py")
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)
B = C.B

AUTHOR = b"Ada " + b"Example"


def _chunk(kind, body):
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))


def png(extra=()):
    ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0))
    iccp = _chunk(b"iCCP", b"icc\x00\x00" + zlib.compress(b"profile"))
    idat = _chunk(b"IDAT", zlib.compress(b"\x00\x00"))
    return B.PNG_SIG + ihdr + iccp + b"".join(extra) + idat + _chunk(b"IEND", b"")


def jpeg():
    def seg(marker, body):
        return b"\xff" + bytes([marker]) + struct.pack(">H", len(body) + 2) + body
    return (b"\xff\xd8" + seg(0xE1, b"Exif\x00\x00" + AUTHOR)
            + seg(0xE2, b"ICC_PROFILE\x00profile")
            + seg(0xE1, b"http://ns.adobe.com/xap/1.0/\x00<x:xmpmeta/>")
            + seg(0xED, b"Photoshop 3.0\x00")
            + seg(0xDA, b"\x00\x01") + b"\x12\x34\xff\xd9")


def pdf():
    xmp = b"<x:xmpmeta xmlns:x='adobe:ns:meta/'><dc:creator>" + AUTHOR + b"</dc:creator></x:xmpmeta>"
    return (b"%PDF-1.4\n1 0 obj << /Author (" + AUTHOR + b") /Creator <FEFF0041>"
            b" /Producer (tool) >> endobj\n2 0 obj << /Type /Metadata /Length "
            + str(len(xmp)).encode() + b" >> stream\n" + xmp + b"\nendstream endobj\n%%EOF\n")


def docx(custom=True):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", '<Types><Override PartName="/docProps/custom.xml" '
                   'ContentType="x"/><Override PartName="/word/document.xml" ContentType="y"/></Types>')
        z.writestr("_rels/.rels", '<Relationships><Relationship Id="r1" Target="docProps/custom.xml"/>'
                   '<Relationship Id="r2" Target="word/document.xml"/></Relationships>')
        z.writestr("docProps/core.xml", "<cp:coreProperties><dc:creator>" + AUTHOR.decode()
                   + "</dc:creator><cp:lastModifiedBy>" + AUTHOR.decode()
                   + "</cp:lastModifiedBy><dc:title>Kept</dc:title></cp:coreProperties>")
        if custom:
            z.writestr("docProps/custom.xml", "<Properties/>")
        z.writestr("word/document.xml", "<w:document>body</w:document>")
    return buf.getvalue()


def test_png_text_and_exif_found_and_stripped_keeping_colour():
    data = png([_chunk(b"tEXt", b"Author\x00" + AUTHOR), _chunk(b"eXIf", b"MM\x00*"),
                _chunk(b"iTXt", b"XML:com.adobe.xmp\x00\x00\x00\x00\x00<x/>")])
    assert len(B.check_png(data)) == 3
    fixed = B.fix_png(data)
    assert B.check_png(fixed) == []
    assert AUTHOR not in fixed and b"iCCP" in fixed and b"IDAT" in fixed
    assert fixed.endswith(_chunk(b"IEND", b""))


def test_clean_png_has_no_findings():
    assert B.check_png(png()) == []


def test_jpeg_exif_xmp_iptc_dropped_icc_kept():
    data = jpeg()
    kinds = sorted(d.split()[1] for _c, d in B.check_jpeg(data))
    assert kinds == ["EXIF", "IPTC", "XMP"]
    fixed = B.fix_jpeg(data)
    assert B.check_jpeg(fixed) == []
    assert AUTHOR not in fixed and b"ICC_PROFILE" in fixed
    assert fixed.endswith(b"\x12\x34\xff\xd9")


def test_pdf_author_creator_xmp_blanked_same_length():
    data = pdf()
    details = [d for _c, d in B.check_pdf(data)]
    assert "/Author is set" in details and "/Creator is set" in details
    assert "XMP metadata packet present" in details
    fixed = B.fix_pdf(data)
    assert len(fixed) == len(data), "same length keeps xref offsets valid"
    assert AUTHOR not in fixed and b"(tool)" in fixed
    assert B.check_pdf(fixed) == []


def test_pdf_metadata_in_compressed_stream_is_reported_not_faked_fixed():
    inner = b"<< /Author (" + AUTHOR + b") >>"
    body = zlib.compress(inner)
    data = b"%PDF-1.5\n3 0 obj << /Filter /FlateDecode >> stream\n" + body + b"\nendstream\n"
    found = B.check_pdf(data)
    assert any("rebuild needed" in d for _c, d in found)
    assert any("rebuild needed" in d for _c, d in B.check_pdf(B.fix_pdf(data)))


def test_docx_creator_and_custom_props_removed():
    data = docx()
    assert len(B.check_ooxml(data)) == 3
    fixed = B.fix_ooxml(data)
    assert B.check_ooxml(fixed) == []
    z = zipfile.ZipFile(io.BytesIO(fixed))
    assert "docProps/custom.xml" not in z.namelist()
    core = z.read("docProps/core.xml").decode()
    assert "<dc:creator></dc:creator>" in core and "<dc:title>Kept</dc:title>" in core
    assert "custom.xml" not in z.read("[Content_Types].xml").decode()
    assert "custom.xml" not in z.read("_rels/.rels").decode()
    assert z.read("word/document.xml") == b"<w:document>body</w:document>"


def test_fix_mode_rewrites_binaries_and_exits_clean(tmp_path):
    (tmp_path / "a.png").write_bytes(png([_chunk(b"tEXt", b"Author\x00" + AUTHOR)]))
    (tmp_path / "b.pdf").write_bytes(pdf())
    (tmp_path / "c.docx").write_bytes(docx())
    out = io.StringIO()
    code, res = C.run([str(tmp_path)], mode="fix", git="none", stream=out)
    assert code == 0, out.getvalue()
    assert res["roots"][0]["fixed_files"] == 3
    code, res = C.run([str(tmp_path)], mode="fail", git="none", stream=io.StringIO())
    assert code == 0 and res["file_findings"] == 0


def test_fail_mode_exits_nonzero_on_binary_finding(tmp_path):
    (tmp_path / "c.docx").write_bytes(docx(custom=False))
    code, res = C.run([str(tmp_path)], mode="fail", git="none", stream=io.StringIO())
    assert code == 1
    assert res["roots"][0]["findings"] == {"office-metadata": 2}
