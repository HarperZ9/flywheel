"""Pins come from the frozen document, or they do not come at all.

`rung_pins.py` is the only place that decides where a rung pin originates. These
tests cover that half: the freeze binding refuses an edited preregistration, the
tables parse completely, and a document that contradicts itself is an error
rather than a silent last-one-wins. What the store actually holds is
`test_rung_digests.py`.
"""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "rung_pins", ROOT / "scripts" / "rung_pins.py")
P = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(P)

FREEZE = json.loads((ROOT / "artifacts" / "prereg" / "FREEZE.json")
                    .read_text(encoding="utf-8"))


def _freeze_at(tmp_path, body: bytes, frozen_sha256: str) -> Path:
    (tmp_path / "prereg.md").write_bytes(body)
    freeze = tmp_path / "FREEZE.json"
    freeze.write_text(json.dumps({
        "prereg_path": "prereg.md", "frozen_sha256": frozen_sha256,
        "prereg_id": "x"}), encoding="utf-8")
    return freeze


# ---- the freeze binding


def test_the_real_prereg_still_matches_the_freeze():
    text, record = P.frozen_prereg(ROOT)
    assert record["frozen_sha256"] == FREEZE["frozen_sha256"]
    assert "All nine rungs are pinned" in text


def test_an_edited_prereg_is_refused(tmp_path):
    """If the document is edited, its pins are no longer the frozen pins. Reading
    pins out of it anyway is the exact failure a preregistration exists to
    prevent."""
    freeze = _freeze_at(tmp_path, b"edited\n", "0" * 64)
    with pytest.raises(P.FreezeMismatch):
        P.frozen_prereg(tmp_path, freeze)


def test_crlf_checkout_hashes_the_same_as_the_committed_blob(tmp_path):
    """The freeze recorded the git blob (LF). A Windows CRLF working tree must
    still verify, or the checker would fail for platform reasons alone."""
    body = "line one\nline two\n"
    want = hashlib.sha256(body.encode()).hexdigest()
    freeze = _freeze_at(tmp_path, body.replace("\n", "\r\n").encode(), want)
    text, _ = P.frozen_prereg(tmp_path, freeze)
    assert text == body


# ---- parsing


def test_all_nine_rungs_parse_with_the_right_pin_kind():
    text, _ = P.frozen_prereg(ROOT)
    pins = P.parse_pins(text)
    assert sorted(pins, key=lambda s: int(s[1:])) == [f"R{i}" for i in range(1, 10)]
    assert {p["kind"] for p in pins.values()} == {"blob", "manifest", "weight"}
    assert pins["R6"]["kind"] == "weight"
    assert pins["R6"]["bytes"] == 19_851_336_480
    assert pins["R8"]["model"] == "olmo2:7b"
    assert P.HEX64.fullmatch(pins["R8"]["manifest_sha256"])
    assert pins["R1"]["kind"] == "blob"
    assert P.BLOB_PIN.fullmatch(pins["R1"]["blob"])


def test_a_rung_pinned_twice_is_an_error():
    dup = ("| rung | model | blob digest |\n|---|---|---|\n"
           "| R1 | `a` | `sha256-" + "a" * 64 + "` |\n"
           "| R1 | `b` | `sha256-" + "b" * 64 + "` |\n")
    with pytest.raises(ValueError, match="pinned twice"):
        P.parse_pins(dup)


def test_a_table_without_a_recognized_digest_column_is_not_parsed():
    """An unrelated table must not be mistaken for a rung table."""
    other = "| rung | model | notes |\n|---|---|---|\n| R1 | `a` | hello |\n"
    assert P.parse_pins(other) == {}


def test_prose_between_tables_does_not_merge_them():
    """Tables are found by header, not position. A paragraph between two tables
    must end the first one, or rows would be read under the wrong pin kind."""
    text = ("| rung | model | blob digest |\n|---|---|---|\n"
            "| R1 | `a` | `sha256-" + "a" * 64 + "` |\n"
            "\nSome prose in between.\n\n"
            "| rung | model | weight sha256 | bytes |\n|---|---|---|---|\n"
            "| R6 | `b` | `" + "b" * 64 + "` | 1,234 |\n")
    pins = P.parse_pins(text)
    assert pins["R1"]["kind"] == "blob"
    assert pins["R6"]["kind"] == "weight"
    assert pins["R6"]["bytes"] == 1234


def test_rungs_are_ordered_by_id_not_by_size():
    text, _ = P.frozen_prereg(ROOT)
    order = [p["rung"] for p in P.pins_in_order(P.parse_pins(text))]
    assert order == [f"R{i}" for i in range(1, 10)]


def test_the_pins_module_names_no_digest_of_its_own():
    """A pin copied into code is a second place to go stale. There must be none."""
    import re
    src = (ROOT / "scripts" / "rung_pins.py").read_text(encoding="utf-8")
    body = "\n".join(l for l in src.splitlines() if "[0-9a-f]" not in l)
    assert not re.search(r"\b[0-9a-f]{64}\b", body)
