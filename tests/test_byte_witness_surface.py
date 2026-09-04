"""The vectors the Flutter surface checks against, pinned to the engine.

desktop/lib/models/byte_witness.dart recomputes witness links in pure Dart. It
can only do that if its canonical encoding is the engine's canonical encoding,
byte for byte, and nothing in a Dart test would notice if the Python side moved
underneath it.

So the vectors live here, produced by the engine itself, and the last test reads
the Dart test file and refuses to pass if the two copies have drifted apart.
A hand-transcribed constant is exactly the thing this repository does not trust.

Every character in this file is ASCII on purpose. The awkward text vector is
spelled with escapes, because a literal U+2028 in a source file is a line break
to some readers and not to others, and a vector nobody can copy safely is not
a vector.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from harness.byte_witness import append, cite, records, witness_bytes

DART_TEST = (Path(__file__).resolve().parent.parent / "desktop" / "test"
             / "byte_witness_test.dart")

FIRST_BYTES = b"hello world"
SECOND_BYTES = b"the quick brown fox"

FIRST = {
    "context": {"kind": "input", "seq": 1},
    "label": "doc/input",
    "length": 11,
    "observed_at": "",
    "prev": "",
    "schema": "flywheel.byte-witness/v1",
    "sha256": "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9",
    "spans": [],
}
FIRST_LINK = "dbe349afee22df36ef03ad06e28f8693b46412c48001e22a1c56567897940be2"

SPAN_SHA = "22c72aa82ce77c82e2ca65a711c79eaa4b51c57f85f91489ceeacc7b385943ba"
SECOND = {
    "context": {"kind": "output", "seq": 1},
    "label": "doc/output",
    "length": 19,
    "observed_at": "",
    "prev": FIRST_LINK,
    "schema": "flywheel.byte-witness/v1",
    "sha256": "9ecb36561341d18eb65484e833efea61edc74b84cf5e6ae1b81c63533e25fc8f",
    "spans": [{"end": 9, "note": "verb phrase", "sha256": SPAN_SHA, "start": 4}],
}
SECOND_LINK = "5d592e36e826fe6f35d25d3627d5ef28f05556dd3408e75866daa6297aa3ce9c"

# Text a naive re-encoder gets wrong: a Latin-1 letter, U+2028 (which some
# encoders escape and Python does not), an astral emoji whose UTF-16 form is a
# surrogate pair, and a context value carrying a tab and a newline.
ODD_LABEL = "odd/\u00e9\u2028\U0001f600"
ODD_CONTEXT = {"note": "tab\there\nnewline", "n": 7, "ok": True}
ODD_LINK = "a93d25123087175d1c2adac11ac7e9fbf6e558db5d4843e60c65bb2b0ad62fe6"


def _chain():
    chain: list = []
    append(chain, FIRST_BYTES, label="doc/input",
           context={"kind": "input", "seq": 1})
    append(chain, SECOND_BYTES, label="doc/output",
           spans=[cite(SECOND_BYTES, 4, 9, "verb phrase")],
           context={"kind": "output", "seq": 1})
    return chain


def test_the_engine_still_produces_the_records_the_surface_checks():
    assert records(_chain()) == [FIRST, SECOND]


def test_the_engine_still_produces_the_links_the_surface_recomputes():
    assert [w.link() for w in _chain()] == [FIRST_LINK, SECOND_LINK]


def test_the_awkward_text_vector_still_hashes_to_what_dart_expects():
    odd = witness_bytes(b"\x00\x01", label=ODD_LABEL, context=ODD_CONTEXT)
    assert odd.link() == ODD_LINK


@pytest.mark.skipif(not DART_TEST.exists(),
                    reason="the Flutter surface is not checked out")
def test_the_dart_surface_carries_these_same_vectors():
    # Not a style check. If either side is edited alone, the Dart verifier is
    # asserting against a record the engine no longer writes, and every verdict
    # it renders after that is about a document nobody has.
    text = DART_TEST.read_text(encoding="utf-8")
    missing = [name for name, value in [
        ("first link", FIRST_LINK),
        ("second link", SECOND_LINK),
        ("odd link", ODD_LINK),
        ("first digest", FIRST["sha256"]),
        ("second digest", SECOND["sha256"]),
        ("span digest", SPAN_SHA),
    ] if value not in text]
    assert not missing, f"the Dart test no longer carries: {', '.join(missing)}"
