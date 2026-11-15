"""Tier A phase 0: the content-free audit receipt.

A team can retain and replay an audit record WITHOUT storing the sensitive text.
The one content-bearing field (findings[].match) is dropped or hashed, verify
still reads Match, and no export path (receipt, JSON, SARIF, console) carries a
verbatim substring. Content-free is not information-free: offsets and counts remain.
"""
import json
import os
import shutil

import pytest

from articulate import receipt
from articulate.cli import main as cli_main

TEXT = "In today's landscape, we leverage cutting-edge synergy to unlock value.\n"
CANARY = "cutting-edge"          # a document word that appears in no rule label or id

_TMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp_audit")


@pytest.fixture()
def work():
    os.makedirs(_TMP, exist_ok=True)
    yield _TMP
    shutil.rmtree(_TMP, ignore_errors=True)


# --- the receipt is content-free ------------------------------------------- #

def test_full_receipt_still_carries_verbatim_text():
    rec = receipt.make_receipt(TEXT, "flavored")
    assert rec["schema"] == "articulate/receipt/v1"
    assert CANARY in json.dumps(rec)                 # the default is content-bearing
    assert all("match" in f for f in rec["findings"])


def test_dropped_receipt_has_no_verbatim_text():
    rec = receipt.make_receipt(TEXT, "flavored", redact="drop")
    assert rec["schema"] == "articulate/receipt/audit/v1"
    assert rec["redaction"] == "drop"
    assert CANARY not in json.dumps(rec)             # no substring survives
    assert all("match" not in f and "match_sha256" not in f for f in rec["findings"])
    assert rec["findings"] and rec["counts"]["high"] >= 1   # offsets/counts remain


def test_hashed_receipt_keeps_a_hash_not_the_text():
    rec = receipt.make_receipt(TEXT, "flavored", redact="hash")
    assert CANARY not in json.dumps(rec)
    assert all("match_sha256" in f and "match" not in f for f in rec["findings"])


# --- and it still replays -------------------------------------------------- #

def test_dropped_receipt_replays_match():
    rec = receipt.make_receipt(TEXT, "flavored", redact="drop")
    assert receipt.verify_receipt(rec, TEXT)[0] == "Match"


def test_hashed_receipt_replays_match():
    rec = receipt.make_receipt(TEXT, "flavored", redact="hash")
    assert receipt.verify_receipt(rec, TEXT)[0] == "Match"


def test_content_free_tampered_is_drift():
    rec = receipt.make_receipt(TEXT, "flavored", redact="drop")
    rec["findings"][0]["category"] = "tampered"
    assert receipt.verify_receipt(rec, TEXT)[0] == "Drift"


def test_content_free_wrong_text_is_unverifiable():
    rec = receipt.make_receipt(TEXT, "flavored", redact="drop")
    assert receipt.verify_receipt(rec, "different clean prose here.\n")[0] == "Unverifiable"


def test_content_free_stale_ruleset_is_unverifiable():
    rec = receipt.make_receipt(TEXT, "flavored", redact="hash")
    rec["ruleset_version"] = "sha256:0000000000000000"
    assert receipt.verify_receipt(rec, TEXT)[0] == "Unverifiable"


# --- the CLI export paths do not leak -------------------------------------- #

def test_cli_receipt_redact_drop_is_content_free(work, capsys):
    p = os.path.join(work, "doc.md")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(TEXT)
    cli_main(["receipt", "--redact", "drop", p])
    out = capsys.readouterr().out
    assert "articulate/receipt/audit/v1" in out and CANARY not in out


def test_cli_check_content_free_console_and_sarif_do_not_leak(work, capsys):
    p = os.path.join(work, "doc.md")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(TEXT)
    cli_main(["check", "--content-free", p])
    assert CANARY not in capsys.readouterr().out
    cli_main(["check", "--content-free", "--sarif", p])
    sarif_out = capsys.readouterr().out
    assert CANARY not in sarif_out and "\"version\": \"2.1.0\"" in sarif_out


def test_cli_check_full_output_does_leak_by_default(work, capsys):
    p = os.path.join(work, "doc.md")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(TEXT)
    cli_main(["check", p])
    assert CANARY in capsys.readouterr().out          # the default still shows text
