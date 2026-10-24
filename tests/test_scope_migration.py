"""The scope migration (project-docs/SCOPE-MIGRATION.md).

Success criteria:
- `scope_of` reads the `scope` field and the older `does_not_prove` field, and
  the older name wins on a pre-migration record that also carries a string
  `scope` label;
- every artifact the migration keeps byte for byte still has the bytes it had
  before the migration (tests/fixtures/scope_migration_kept_bytes.sha256);
- old-version records still verify through today's readers: a frozen v3
  receipt, a v4 receipt, a v2 QA card, a v1 routed receipt, and the captured
  superstack receipts;
- false-success control: a v5 receipt that carries the older name, or a v4
  receipt that carries `scope`, is refused;
- the CI gate finds no stray use of the older name.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from harness.scope import (LEGACY_SCOPE_KEY, SCOPE_KEY, has_both, scope_key,
                           scope_list, scope_of)

ROOT = Path(__file__).resolve().parents[1]
KEPT = ROOT / "tests" / "fixtures" / "scope_migration_kept_bytes.sha256"


# --- the reader ------------------------------------------------------------------

def test_scope_of_reads_the_new_name():
    record = {"schema": "x/v2", SCOPE_KEY: ["the bytes match the recorded digest"]}
    assert scope_of(record) == ["the bytes match the recorded digest"]
    assert scope_key(record) == SCOPE_KEY


def test_scope_of_reads_the_older_name():
    record = {"schema": "x/v1", LEGACY_SCOPE_KEY: ["semantic correctness"]}
    assert scope_of(record) == ["semantic correctness"]
    assert scope_key(record) == LEGACY_SCOPE_KEY


def test_the_older_name_wins_over_a_string_label_on_an_old_record():
    record = {"scope": "task", LEGACY_SCOPE_KEY: ["the summary covers one task"]}
    assert scope_of(record) == ["the summary covers one task"]
    assert not has_both(record)
    assert has_both({SCOPE_KEY: ["a"], LEGACY_SCOPE_KEY: ["b"]})


@pytest.mark.parametrize("value, expected", [
    ("one line", ["one line"]), ("", []), (["a", "b"], ["a", "b"]),
    (("a",), ["a"]), (None, []),
])
def test_scope_list_normalizes_strings_and_lists(value, expected):
    record = {} if value is None else {SCOPE_KEY: value}
    assert scope_list(record) == expected


def test_scope_of_on_something_that_is_not_a_record():
    assert scope_of(None) is None
    assert scope_of(["a"], default=[]) == []


# --- kept bytes ------------------------------------------------------------------

def _kept():
    for line in KEPT.read_text(encoding="utf-8").splitlines():
        digest, path = line.split("  ", 1)
        yield digest, path


def test_the_kept_manifest_is_not_empty():
    assert len(list(_kept())) > 50


@pytest.mark.parametrize("digest, path", list(_kept()))
def test_a_kept_artifact_keeps_its_bytes(digest, path):
    data = (ROOT / path).read_bytes()
    assert hashlib.sha256(data).hexdigest() == digest, path


# --- old versions still verify ---------------------------------------------------

def test_a_frozen_v3_receipt_still_verifies():
    from harness.receipt import LEGACY_SCHEMA, Receipt
    frozen = json.loads((ROOT / "tests/fixtures/receipt_v3_legacy_fixtures.json")
                        .read_text(encoding="utf-8"))
    body = frozen["receipt"]
    receipt = Receipt.from_dict(body)
    assert receipt.schema == LEGACY_SCHEMA
    assert receipt.claim_sha256() == body["claim_sha256"]
    assert receipt.to_dict() == body
    assert LEGACY_SCOPE_KEY in body and SCOPE_KEY not in body


def _receipt(**kw):
    from tests.test_receipt_v2 import _r
    return _r(**kw)


def test_a_v4_receipt_round_trips_with_its_older_vocabulary():
    from harness.receipt import Receipt, V4_SCHEMA
    old = _receipt(schema=V4_SCHEMA)
    wire = old.to_dict()
    assert wire[LEGACY_SCOPE_KEY][0] == "NOT_PROVES_PUBLICATION_COMPLETENESS"
    assert Receipt.from_dict(wire).claim_sha256() == old.claim_sha256()


def test_a_v5_receipt_says_what_it_covers():
    from harness.receipt import Receipt, SCHEMA
    new = _receipt()
    wire = new.to_dict()
    assert wire["schema"] == SCHEMA
    assert wire[SCOPE_KEY][0] == "CHECKED_BY_NAMED_CHECKER"
    assert LEGACY_SCOPE_KEY not in wire
    assert not any("NOT_PROVES" in code for code in wire[SCOPE_KEY])
    assert Receipt.from_dict(wire).claim_sha256() == new.claim_sha256()


def test_a_receipt_carrying_the_other_versions_name_is_refused():
    from harness.receipt import Receipt, V4_SCHEMA
    from harness.receipt_fields import ReceiptError
    new = _receipt().to_dict()
    with pytest.raises(ReceiptError):
        Receipt.from_dict({**new, LEGACY_SCOPE_KEY: new[SCOPE_KEY]})
    old = _receipt(schema=V4_SCHEMA).to_dict()
    with pytest.raises(ReceiptError):
        Receipt.from_dict({**old, SCOPE_KEY: old[LEGACY_SCOPE_KEY]})


@pytest.mark.parametrize("path", sorted(
    str(p.relative_to(ROOT)) for p in (ROOT / "tests/fixtures/raw_native").glob("*/receipt.json")))
def test_a_captured_superstack_receipt_still_verifies(path):
    from harness._vendor import superstack as ss
    rec = json.loads((ROOT / path).read_text(encoding="utf-8"))
    assert LEGACY_SCOPE_KEY in rec
    assert ss.verify_receipt(rec) == []


# --- the gate ---------------------------------------------------------------------

def test_the_gate_finds_no_stray_use_of_the_older_name(capsys):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "check_scope_migration", ROOT / "scripts" / "check_scope_migration.py")
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    assert gate.main([]) == 0, capsys.readouterr().out
