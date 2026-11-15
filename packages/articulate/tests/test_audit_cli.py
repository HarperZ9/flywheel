"""Tier A phase 1: the reviewer/timestamp envelope and the `articulate audit` CLI.

The envelope records who screened a text and when, as issuance provenance that
never enters the verified core. The audit CLI queries committed receipts locally:
recorded verdicts, blocked rules, stale-ruleset and recent counts, and (with
--reverify) whether each receipt still holds against its source, failing the gate
only on a real integrity break (drift, a source that changed since screening, or
an unreadable source), never on an honest sub-threshold abstention.
"""
import json
import os
import shutil
from datetime import datetime

import pytest

from articulate import receipt
from articulate.cli import main as cli_main

TEXT = "In today's landscape, we leverage cutting-edge synergy to unlock value.\n"
LONG_CLEAN = (
    "The team met on Tuesday to plan the next release. They agreed on the dates, "
    "assigned each task to a named owner, and set a short check-in for Friday "
    "morning to confirm the work had landed before the weekend arrived.\n"
)

_TMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp_auditcli")


@pytest.fixture()
def work():
    os.makedirs(_TMP, exist_ok=True)
    yield _TMP
    shutil.rmtree(_TMP, ignore_errors=True)


def _commit(dirpath, rec_name, src_name, content, **kw):
    src = os.path.join(dirpath, src_name)
    with open(src, "w", encoding="utf-8", newline="") as fh:   # no CRLF translation
        fh.write(content)
    # Hash exactly what lands on disk, the way the CLI reads it (rb -> decode).
    with open(src, "rb") as fh:
        text = fh.read().decode("utf-8")
    rec = receipt.make_receipt(text, "flavored", **kw)
    rec["file"] = src
    with open(os.path.join(dirpath, rec_name), "w", encoding="utf-8") as fh:
        json.dump(rec, fh)
    return src


# --- the envelope ---------------------------------------------------------- #

def test_receipt_carries_created_at_and_reviewer():
    rec = receipt.make_receipt(TEXT, "flavored", reviewer="alice",
                               created_at="2026-01-01T00:00:00+00:00")
    assert rec["created_at"] == "2026-01-01T00:00:00+00:00" and rec["reviewer"] == "alice"


def test_created_at_defaults_to_valid_iso_and_reviewer_is_none():
    rec = receipt.make_receipt(TEXT, "flavored")
    datetime.fromisoformat(rec["created_at"])       # parses without error
    assert rec["reviewer"] is None


def test_envelope_is_provenance_not_load_bearing():
    rec = receipt.make_receipt(TEXT, "flavored", reviewer="alice",
                               created_at="2026-01-01T00:00:00+00:00")
    assert receipt.verify_receipt(rec, TEXT)[0] == "Match"
    rec["reviewer"] = "mallory"
    rec["created_at"] = "1999-01-01T00:00:00+00:00"
    assert receipt.verify_receipt(rec, TEXT)[0] == "Match"   # not re-derived, not compared


def test_receipt_cli_records_reviewer(work, capsys):
    src = os.path.join(work, "a.md")
    with open(src, "w", encoding="utf-8") as fh:
        fh.write(TEXT)
    cli_main(["receipt", "--reviewer", "alice", src])
    rec = json.loads(capsys.readouterr().out)
    assert rec["reviewer"] == "alice" and "created_at" in rec


# --- the audit query ------------------------------------------------------- #

def test_audit_summarizes_committed_receipts(work, capsys):
    _commit(work, "a.json", "a.md", TEXT)          # flagged / blocked
    _commit(work, "b.json", "b.md", LONG_CLEAN)    # clean / ok
    rc = cli_main(["audit", work, "--json"])
    out = json.loads(capsys.readouterr().out)
    assert out["receipts"] == 2
    assert out["by_gate"].get("blocked") == 1 and out["by_gate"].get("ok") == 1
    assert out["blocked_by_rule"] and rc == 0


def test_audit_flags_stale_ruleset(work, capsys):
    _commit(work, "a.json", "a.md", TEXT)
    p = os.path.join(work, "a.json")
    with open(p, encoding="utf-8") as fh:
        rec = json.load(fh)
    rec["ruleset_version"] = "sha256:0000deadbeef"
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(rec, fh)
    cli_main(["audit", work, "--json"])
    assert json.loads(capsys.readouterr().out)["stale_ruleset"] == 1


# --- reverify and the gate ------------------------------------------------- #

def test_reverify_match_passes_the_gate(work, capsys):
    _commit(work, "a.json", "a.md", TEXT)
    rc = cli_main(["audit", work, "--reverify", "--gate", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert out["reverify"].get("Match") == 1 and rc == 0


def test_reverify_source_changed_fails_the_gate(work, capsys):
    src = _commit(work, "a.json", "a.md", TEXT)
    with open(src, "a", encoding="utf-8") as fh:
        fh.write("We also leverage more synergy here.\n")     # edited since screening
    rc = cli_main(["audit", work, "--reverify", "--gate", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert out["reverify"].get("source-changed") == 1 and rc == 1


def test_reverify_source_missing_is_informational(work, capsys):
    src = _commit(work, "a.json", "a.md", TEXT)
    os.remove(src)
    rc = cli_main(["audit", work, "--reverify", "--gate", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert out["reverify"].get("source-missing") == 1 and rc == 0   # missing is not drift


def test_reverify_subthreshold_does_not_fail_the_gate(work, capsys):
    _commit(work, "a.json", "a.md", "Thanks, will review shortly.\n")   # short + clean
    rc = cli_main(["audit", work, "--reverify", "--gate", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert out["reverify"].get("Unverifiable") == 1 and rc == 0        # honest abstention
