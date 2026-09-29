"""The custody ledger: hash-chained metadata, a head anchor, no content.

I15: custody events append metadata-only entries to a chain the owner reads.
A truncated ledger is caught through its head anchor, the method mneme uses
for its audit log. Keys outside a kind's allowlist, and free text anywhere,
are refused before anything is written.
"""
import json

import pytest

from harness.trace_custody_ledger import CustodyLedger, LedgerError

OWNER = "owner_" + "a" * 32
DIGEST = "d" * 64


@pytest.fixture
def ledger(tmp_path):
    return CustodyLedger(tmp_path, OWNER)


def _deletion(**extra):
    fields = {"plan_digest": DIGEST, "stores": ["S1"], "items": 2,
              "reason_code": "owner_request", "presence": "none"}
    fields.update(extra)
    return fields


def test_append_then_verify_walks_the_chain(ledger):
    first = ledger.append("deletion", _deletion())
    second = ledger.append("export", {"root_digest": DIGEST, "items": 3,
                                      "presence": "none", "redaction": "credentials"})
    assert first["seq"] == 0 and second["seq"] == 1
    assert second["prior_sha256"] == first["entry_sha256"]
    report = ledger.verify()
    assert report["ok"] is True and report["entries"] == 2
    assert report["head"] == second["entry_sha256"]
    assert [e["kind"] for e in ledger.entries()] == ["deletion", "export"]


def test_truncated_ledger_is_caught_by_the_head_anchor(ledger):
    for _ in range(3):
        ledger.append("deletion", _deletion())
    lines = ledger.path.read_bytes().splitlines(keepends=True)
    ledger.path.write_bytes(b"".join(lines[:2]))
    report = ledger.verify()
    assert report["ok"] is False and report["reason"] == "TRUNCATED"


def test_edited_entry_breaks_the_chain(ledger):
    ledger.append("deletion", _deletion())
    ledger.append("deletion", _deletion(items=5))
    lines = ledger.path.read_text(encoding="utf-8").splitlines()
    edited = json.loads(lines[0]); edited["fields"]["items"] = 99
    lines[0] = json.dumps(edited, sort_keys=True, separators=(",", ":"))
    ledger.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report = ledger.verify()
    assert report["ok"] is False and report["reason"] in {"ENTRY_DIGEST", "CHAIN_BROKEN"}


def test_anchor_one_behind_after_a_crash_is_recovered_not_tamper(ledger, monkeypatch):
    ledger.append("deletion", _deletion())
    from harness.trace_chain_log import ChainedLog
    monkeypatch.setattr(ChainedLog, "_write_anchor", lambda *a, **k: None)
    ledger.append("deletion", _deletion())
    monkeypatch.undo()
    report = ledger.verify()
    assert report["ok"] is True and report["anchor_behind"] == 1
    ledger.append("deletion", _deletion())
    after = ledger.verify()
    assert after["ok"] is True and after["anchor_behind"] == 0
    assert after["entries"] == 3


@pytest.mark.parametrize("kind, fields", [
    ("deletion", _deletion(prompt="the text of a prompt")),
    ("deletion", _deletion(reason_code="free text with spaces")),
    ("deletion", _deletion(stores=["S1", "a path/../x y"])),
    ("no-such-kind", {"items": 1}),
    ("export", {"root_digest": DIGEST, "items": 1, "presence": "none",
                "redaction": "credentials", "destination": "C:/Users/x/out"}),
])
def test_unknown_kinds_keys_and_free_text_are_refused(ledger, kind, fields):
    with pytest.raises(LedgerError):
        ledger.append(kind, fields)
    assert not ledger.path.exists() or ledger.path.read_bytes() == b""


def test_a_missing_ledger_verifies_as_empty_and_writes_nothing(tmp_path):
    ledger = CustodyLedger(tmp_path, OWNER)
    assert ledger.verify() == {"ok": True, "entries": 0, "head": "0" * 64,
                               "anchor_behind": 0}
    assert list(tmp_path.iterdir()) == []


def test_entries_never_carry_a_value_outside_the_metadata_grammar(ledger):
    entry = ledger.append("capture_count", {"client": "claude-code", "turns": 4,
                                            "failures": 0, "suppressed": 1})
    raw = json.dumps(entry)
    assert set(entry) == {"schema", "seq", "kind", "at", "fields",
                          "prior_sha256", "entry_sha256"}
    assert " " not in raw.replace(", ", ",").replace(": ", ":")
