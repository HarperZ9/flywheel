"""SP-18, I5: a tombstone records that a deletion happened, when, why and in
which classes, and carries no fingerprint, no path and no session id. The
deletion ledger is hash chained with a head anchor, so truncation is caught."""
import hashlib
import json

import pytest

from harness.trace_tombstones import TombstoneError, TombstoneLedger

OWNER = "owner_" + "a" * 32
CANARY = "SHORT-CANARY-9f8e7d6c5b4a"
SESSION = "0f6d2c1e-4b7a-4c55-9a51-2f0e7c9d1a3b"


def _fields(**extra):
    fields = {"plan_digest": "d" * 64, "stores": ["S1", "S7"], "counts": {"C1": 2, "C4": 3},
              "reason_code": "owner_request", "started_at": "2026-09-26T12:00:00Z",
              "residual": {"S1": 0, "S7": 0}, "residue": {"freed_clusters": 1},
              "out_of_reach": {"client_transcript": 1}, "presence": "none",
              "checks": ["scan_set", "keys_absent"]}
    fields.update(extra)
    return fields


@pytest.fixture
def ledger(tmp_path):
    (tmp_path / "state").mkdir()
    return TombstoneLedger(tmp_path / "state", OWNER)


def test_a_tombstone_holds_no_fingerprint_path_or_session(ledger):
    entry = ledger.append(**_fields())
    text = ledger.path.read_text()
    digest = hashlib.sha256(CANARY.encode()).hexdigest()
    assert CANARY not in text and digest[:12] not in text and SESSION not in text
    values = json.dumps({k: v for k, v in entry.items() if k != "schema"})
    assert "\\" not in values and "/" not in values
    assert entry["tombstone_ref"].startswith("tomb_") and entry["seq"] == 0


@pytest.mark.parametrize("bad", [{"reason_code": "C:/Users/x"}, {"stores": ["S1", SESSION]},
                                 {"counts": {"C1": "two"}},
                                 {"out_of_reach": {"client_transcript": "~/.claude"}}])
def test_free_text_paths_and_session_ids_are_refused(ledger, bad):
    with pytest.raises(TombstoneError):
        ledger.append(**_fields(**bad))
    assert not ledger.path.exists() or ledger.path.read_bytes() == b""


def test_the_chain_verifies_and_links_each_entry(ledger):
    first = ledger.append(**_fields())
    second = ledger.append(**_fields(plan_digest="e" * 64))
    assert second["prior_sha256"] == first["entry_sha256"]
    report = ledger.verify()
    assert report["ok"] and report["entries"] == 2


def test_truncation_is_caught_by_the_head_anchor(ledger):
    for index in range(3):
        ledger.append(**_fields(plan_digest=f"{index}" * 64))
    lines = ledger.path.read_bytes().splitlines(keepends=True)
    ledger.path.write_bytes(b"".join(lines[:2]))
    assert ledger.verify() == {"ok": False, "reason": "TRUNCATED"}


def test_an_edited_entry_breaks_the_chain(ledger):
    ledger.append(**_fields())
    doc = json.loads(ledger.path.read_bytes())
    doc["counts"]["C1"] = 99
    ledger.path.write_bytes(json.dumps(doc).encode() + b"\n")
    assert ledger.verify()["ok"] is False
