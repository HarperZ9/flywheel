"""P0-e: binary and unsupported-document inputs fail closed with an explicit
reason, so a .docx or an image is refused instead of returning a spurious clean
scan of lossy-decoded bytes. UTF-8 non-English text must still pass.
"""
import os
import shutil

import pytest

from articulate import detector
from articulate.cli import main as cli_main

_TMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp_bin")

# A real Zip local-file header, as a .docx begins.
DOCX_MAGIC = b"PK\x03\x04\x14\x00\x06\x00" + b"\x00" * 26


@pytest.fixture()
def work():
    os.makedirs(_TMP, exist_ok=True)
    yield _TMP
    shutil.rmtree(_TMP, ignore_errors=True)


def test_binary_reason_detects_magic_bytes():
    assert detector.binary_reason(DOCX_MAGIC)               # zip/docx
    assert detector.binary_reason(b"%PDF-1.7\n%rest")       # pdf
    assert detector.binary_reason(b"\x89PNG\r\n\x1a\n....")  # png
    assert detector.binary_reason(b"plain\x00text")         # embedded null


def test_binary_reason_by_extension_even_when_bytes_look_texty():
    assert detector.binary_reason(b"this could be read as text", name="report.docx")
    assert detector.binary_reason(b"x", name="/tmp/a.pdf")


def test_plain_and_non_english_text_are_not_refused():
    assert detector.binary_reason(b"Hello, this is plain prose.\n", name="a.md") is None
    fr = "Voilà une phrase en français avec des accents éè.\n".encode("utf-8")
    assert detector.binary_reason(fr, name="notes.txt") is None
    ja = "これは日本語の文です。\n".encode("utf-8")
    assert detector.binary_reason(ja, name="notes.txt") is None


def test_cli_refuses_a_docx_and_fails_the_gate(work, capsys):
    p = os.path.join(work, "paper.docx")
    with open(p, "wb") as fh:
        fh.write(DOCX_MAGIC)
    rc = cli_main(["check", "--gate", p])
    err = capsys.readouterr().err
    assert rc == 1                                   # fail closed on the gate
    assert "cannot screen" in err and "paper.docx" in err


def test_cli_receipt_refuses_binary(work, capsys):
    p = os.path.join(work, "img.png")
    with open(p, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20)
    cli_main(["receipt", p])
    assert "cannot screen" in capsys.readouterr().err


def test_cli_still_screens_a_normal_text_file(work, capsys):
    p = os.path.join(work, "doc.md")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("We leverage synergy to unlock value across the board.\n")
    rc = cli_main(["check", "--gate", p])
    out = capsys.readouterr().out
    assert rc == 1                                   # a real HIGH device still gates
    assert "high" in out
