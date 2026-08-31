"""ledger.verify() must return a verdict on hostile ledger bytes, never raise.

A stranger runs `Ledger(path).verify()` over a JSONL log a distrusted author
handed them. verify() promises a named verdict (MATCH / DRIFT / UNVERIFIABLE), so
every shape a file can hold has to reach one of those, not a traceback.

Four escapes this pins down, each reproduced against the current code:

  V1  a row missing `entry_hash` -- the equality check reads it OUTSIDE the
      per-entry try, so a KeyError escapes instead of naming DRIFT.
  V2  a non-string `key` -- reached on the MATCH path through root() -> _leaves(),
      where `key.encode()` raises AttributeError because an int has no .encode.
  V3  a lone-surrogate `key` -- same site: the surrogate survives canonical JSON
      (escaped to ASCII) but has no UTF-8 form, so `key.encode()` raises
      UnicodeEncodeError.
  V4  a non-UTF-8 file -- read_text(encoding="utf-8") raises UnicodeDecodeError, a
      ValueError sibling that slips past the `except LedgerError` guarding the read.
"""
import json

import receipt_factories as factories
from harness.ledger import Ledger
from harness.receipt_sign import unsigned


def test_verify_names_a_row_missing_entry_hash_instead_of_crashing(tmp_path):
    p = tmp_path / "log.jsonl"
    Ledger(p).append(unsigned(factories.receipt()))
    row = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    del row["entry_hash"]
    p.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")
    v = Ledger(p).verify()                              # must not raise
    assert v["verdict"] in {"DRIFT", "UNVERIFIABLE"}
    assert v["broken_at"] == 0


def test_verify_names_a_non_string_key_instead_of_crashing(tmp_path):
    # A self-consistent row whose key is an int reaches the MATCH path, where
    # _leaves() does key.encode() and an int has no .encode.
    p = tmp_path / "log.jsonl"
    led = Ledger(p)
    led.append_record("receipt", 123, {"payload": "x"})
    v = led.verify()                                    # must not raise
    assert v["verdict"] == "MATCH"


def test_verify_names_a_surrogate_key_instead_of_crashing(tmp_path):
    # Same site: a lone surrogate is self-consistent through the digest chain but
    # has no UTF-8 form, so key.encode() raises UnicodeEncodeError at the leaf.
    p = tmp_path / "log.jsonl"
    led = Ledger(p)
    led.append_record("receipt", "\ud800", {"payload": "x"})
    v = led.verify()                                    # must not raise
    assert v["verdict"] == "MATCH"


def test_verify_names_a_non_utf8_file_instead_of_crashing(tmp_path):
    # read_text(encoding="utf-8") raises UnicodeDecodeError, which is not a
    # LedgerError, so it escapes the read guard in verify().
    p = tmp_path / "log.jsonl"
    p.write_bytes(b"\xff\xfe not valid utf-8\n")
    v = Ledger(p).verify()                              # must not raise
    assert v["verdict"] == "UNVERIFIABLE"
    assert v["size"] == 0
