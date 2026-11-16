"""Input kinds read from the item itself: one case per detectable kind, and the unknown answer."""
from __future__ import annotations

import io
import json
import struct
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from plexus.kinds import CALLER_ONLY, KINDS, detect  # noqa: E402

WAV = b"RIFF" + struct.pack("<I", 36) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, 8000, 16000, 2, 16) + b"data\x00\x00\x00\x00"


def _zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("a.txt", "x")
    return buf.getvalue()


def _tar() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as t:
        info = tarfile.TarInfo("a.txt")
        info.size = 1
        t.addfile(info, io.BytesIO(b"x"))
    return buf.getvalue()


FILES = {
    # name: (bytes, kinds that must be present)
    "a.png": (b"\x89PNG\r\n\x1a\n" + b"\x00" * 40, {"file", "image"}),
    "a.jpg": (b"\xff\xd8\xff\xe0" + b"\x00" * 40, {"image"}),
    "a.gif": (b"GIF89a" + b"\x00" * 40, {"image"}),
    "a.webp": (b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 40, {"image"}),
    "a.pdf": (b"%PDF-1.7\n" + b"\x00" * 40, {"pdf"}),
    "2401.12345.pdf": (b"%PDF-1.7\n" + b"\x00" * 40, {"pdf", "paper"}),
    "a.zip": (_zip(), {"archive"}),
    "a.docx": (_zip(), {"archive"}),
    "a.tar": (_tar(), {"archive"}),
    "a.gz": (b"\x1f\x8b\x08" + b"\x00" * 40, {"archive"}),
    "a.wav": (WAV, {"audio"}),
    "a.flac": (b"fLaC" + b"\x00" * 40, {"audio"}),
    "a.mp3": (b"ID3\x04" + b"\x00" * 40, {"audio"}),
    "a.mkv": (b"\x1aE\xdf\xa3" + b"\x00" * 40, {"video", "audio"}),
    "a.mp4": (b"\x00\x00\x00\x18ftypisom" + b"\x00" * 40, {"video", "audio"}),
    "a.m4a": (b"\x00\x00\x00\x18ftypM4A " + b"\x00" * 40, {"audio"}),
    "a.glb": (b"glTF\x02\x00\x00\x00" + b"\x00" * 40, {"model3d"}),
    "a.obj": (b"v 0 0 0\nv 1 0 0\nf 1 2 1\n", {"model3d"}),
    "a.db": (b"SQLite format 3\x00" + b"\x00" * 90, {"table"}),
    "a.svg": (b'<svg xmlns="http://www.w3.org/2000/svg"><circle r="1"/></svg>', {"vector"}),
    "a.html": (b"<!doctype html><html><body>hi</body></html>", {"html"}),
    "a.xml": (b'<?xml version="1.0"?><rss version="2.0"><channel/></rss>', {"feed"}),
    "a.csv": (b"t,v\n0,1\n1,2\n2,3\n", {"table", "series"}),
    "s.csv": (b"wavelength_nm,power\n400,1\n500,2\n600,3\n", {"table", "series", "spectrum"}),
    "a.md": (b"# Title\n\nSome words for a reader.\n", {"prose"}),
    "a.py": (b"print('hi')\n", {"code"}),
    "a.bld": (b"fn main() {}\n", {"code"}),
    "t.json": (json.dumps({"thesis": "x", "claims": []}).encode(), {"claim"}),
    "l.json": (json.dumps({"surfaces": [{"radius": 10, "glass": "N-BK7"}]}).encode(), {"lens"}),
    "c.json": (json.dumps({"components": [], "nets": []}).encode(), {"circuit"}),
    "p.json": (json.dumps({"author": "a", "date": "2026-01-01", "text": "t"}).encode(), {"post"}),
    "r.json": (json.dumps([{"a": 1}, {"a": 2}]).encode(), {"table"}),
}


@pytest.mark.parametrize("name", sorted(FILES))
def test_file_kinds_come_from_the_bytes(tmp_path, name):
    data, want = FILES[name]
    p = tmp_path / name
    p.write_bytes(data)
    got = detect(str(p))
    assert want <= set(got["kinds"]), (name, got)
    assert got["unknown"] is False and all(got["evidence"][k] for k in got["kinds"])


def test_an_extension_alone_does_not_make_a_picture(tmp_path):
    p = tmp_path / "liar.png"
    p.write_bytes(b"just some text, not a picture\n")
    assert "image" not in detect(str(p))["kinds"]


def test_sidecar_beside_a_picture_makes_it_a_post(tmp_path):
    (tmp_path / "x.png").write_bytes(FILES["a.png"][0])
    assert "post" not in detect(str(tmp_path / "x.png"))["kinds"]
    (tmp_path / "x.md").write_text("author, date, text", encoding="utf-8")
    assert {"image", "post"} <= set(detect(str(tmp_path / "x.png"))["kinds"])


def test_folder_and_repo(tmp_path):
    assert detect(str(tmp_path))["kinds"] == ["folder"]
    (tmp_path / ".git").mkdir()
    assert set(detect(str(tmp_path))["kinds"]) == {"folder", "repo"}


@pytest.mark.parametrize("url, want", [
    ("https://example.org/page", {"web"}),
    ("https://www.reddit.com/r/a/comments/b", {"web", "post"}),
    ("https://x.com/user/status/1", {"web", "post"}),
    ("https://arxiv.org/abs/2401.00001", {"web", "paper"}),
    ("https://example.org/feed", {"web", "feed"}),
    ("https://example.org/a/picture.png", {"web", "image"}),
    ("https://example.org/a/paper.pdf", {"web", "pdf"}),
])
def test_url_kinds_come_from_the_shape(url, want):
    assert set(detect(url)["kinds"]) == want


@pytest.mark.parametrize("text, want", [
    ("#b46f00", "colour"), ("ff0000", "colour"), ("rgb(255, 0, 0)", "colour"),
    ("2401.12345", "paper"), ("10.1038/nature12373", "paper"),
    ("optics.f_number/1", "formula"), ("42", "seed"),
    ("the sky is blue today", "prose"), ('{"claims": [], "thesis": "t"}', "claim"),
])
def test_literal_kinds(text, want):
    assert detect(text)["kinds"] == [want]


@pytest.mark.parametrize("item, reason", [
    ("", "empty item"), ("C:/no/such/place/x.png", "no such path"), ("zz", "no kind fits"),
])
def test_unknown_when_nothing_fits(item, reason):
    got = detect(item)
    assert got["unknown"] is True and got["kinds"] == [] and got["reason"] == reason


def test_unrecognised_bytes_are_only_a_file_and_unknown(tmp_path):
    p = tmp_path / "blob.bin"
    p.write_bytes(bytes(range(256)) * 4)
    got = detect(str(p))
    assert got["kinds"] == ["file"] and got["unknown"] is True


def test_every_kind_is_detected_by_some_case_or_named_as_caller_only():
    seen = set()
    for data, want in FILES.values():
        seen |= want
    seen |= {"web", "post", "paper", "feed", "folder", "repo", "colour", "formula", "seed",
             "prose", "claim", "file"}
    missing = set(KINDS) - seen - set(CALLER_ONLY)
    assert missing == set(), missing
    assert set(CALLER_ONLY) <= set(KINDS)
