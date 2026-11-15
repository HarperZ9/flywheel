"""Regression tests for the audit-layer adversarial review (wf w18p2x3je).

Each pins a confirmed finding: a content-free receipt must not leak the flagged
word through exact offsets plus a self-describing rule_id; verify must reject a
mislabeled or smuggling receipt; and the audit CLI must not crash on a malformed
receipt nor read a cosmetic line-ending rewrite as a source change.
"""
import json
import os
import shutil

import pytest

from articulate import receipt
from articulate.cli import main as cli_main

TEXT = "In today's landscape, we leverage cutting-edge synergy to unlock value.\n"
_TMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp_hard")


@pytest.fixture()
def work():
    os.makedirs(_TMP, exist_ok=True)
    yield _TMP
    shutil.rmtree(_TMP, ignore_errors=True)


def _put(dirp, name, obj):
    with open(os.path.join(dirp, name), "w", encoding="utf-8") as fh:
        json.dump(obj, fh)


# --- Fix A: no offset/length oracle in a content-free record --------------- #

def test_content_free_findings_carry_no_offsets_or_label():
    for mode in ("drop", "hash"):
        rec = receipt.make_receipt(TEXT, "flavored", redact=mode)
        for f in rec["findings"]:
            assert not ({"start", "end", "col", "match", "label"} & set(f))
            assert set(f) <= {"rule_id", "tier", "category", "line", "match_sha256"}


def test_content_free_still_replays_match():
    for mode in ("drop", "hash"):
        rec = receipt.make_receipt(TEXT, "flavored", redact=mode)
        assert receipt.verify_receipt(rec, TEXT)[0] == "Match"


def test_content_free_check_json_and_sarif_carry_no_offsets(work, capsys):
    p = os.path.join(work, "d.md")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(TEXT)
    cli_main(["check", "--content-free", "--json", p])
    payload = json.loads(capsys.readouterr().out)
    for r in payload["results"]:
        for f in r["high"] + r["medium"] + r["low"]:
            assert not ({"start", "end", "col", "match", "label", "snippet"} & set(f))
    cli_main(["check", "--content-free", "--sarif", p])
    sarif = json.loads(capsys.readouterr().out)
    for res in sarif["runs"][0]["results"]:
        assert set(res["locations"][0]["physicalLocation"]["region"]) == {"startLine"}
    for rule in sarif["runs"][0]["tool"]["driver"]["rules"]:
        assert "leverage" not in rule["shortDescription"]["text"]   # no enumerating label


# --- Fix B: verify rejects a mislabeled or smuggling receipt ---------------- #

def test_full_receipt_relabeled_audit_is_unverifiable():
    rec = receipt.make_receipt(TEXT, "flavored")     # full: verbatim match present
    rec["schema"] = receipt.AUDIT_SCHEMA             # lie about being content-free
    assert receipt.verify_receipt(rec, TEXT)[0] == "Unverifiable"


def test_content_free_receipt_smuggling_a_match_is_unverifiable():
    rec = receipt.make_receipt(TEXT, "flavored", redact="drop")
    rec["findings"][0]["match"] = "leverage"         # smuggle verbatim text back in
    assert receipt.verify_receipt(rec, TEXT)[0] == "Unverifiable"


def test_full_receipt_declaring_a_redaction_is_unverifiable():
    rec = receipt.make_receipt(TEXT, "flavored")
    rec["redaction"] = "drop"
    assert receipt.verify_receipt(rec, TEXT)[0] == "Unverifiable"


# --- Fix C/E: audit survives malformed receipts, and bounds "recent" ------- #

def test_audit_survives_non_string_created_at(work, capsys):
    _put(work, "a.json", {"schema": receipt.SCHEMA, "gate": "ok", "verdict": "clean",
                          "created_at": 123, "findings": []})
    rc = cli_main(["audit", work, "--json"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["receipts"] == 1 and out["recent_30d"] == 0


def test_audit_survives_null_findings_on_a_blocked_receipt(work, capsys):
    _put(work, "a.json", {"schema": receipt.SCHEMA, "gate": "blocked", "verdict": "flagged",
                          "created_at": "2026-09-17T00:00:00+00:00", "findings": None})
    rc = cli_main(["audit", work, "--json"])
    assert rc == 0 and json.loads(capsys.readouterr().out)["receipts"] == 1


def test_audit_future_dated_receipt_is_not_recent(work, capsys):
    _put(work, "a.json", {"schema": receipt.SCHEMA, "gate": "ok", "verdict": "clean",
                          "created_at": "2099-01-01T00:00:00+00:00", "findings": []})
    cli_main(["audit", work, "--json"])
    assert json.loads(capsys.readouterr().out)["recent_30d"] == 0


# --- Fix D: a CRLF rewrite is not a false source-changed ------------------- #

def test_crlf_rewrite_is_not_a_source_change(work, capsys):
    src = os.path.join(work, "a.md")
    with open(src, "wb") as fh:
        fh.write(TEXT.encode("utf-8"))               # LF on disk
    cli_main(["receipt", src])
    rec_json = capsys.readouterr().out
    with open(os.path.join(work, "a.json"), "w", encoding="utf-8") as fh:
        fh.write(rec_json)
    with open(src, "wb") as fh:                       # rewrite to CRLF, same words
        fh.write(TEXT.replace("\n", "\r\n").encode("utf-8"))
    rc = cli_main(["audit", work, "--reverify", "--gate", "--json"])
    out = json.loads(capsys.readouterr().out)
    assert out["reverify"].get("source-changed", 0) == 0 and rc == 0
