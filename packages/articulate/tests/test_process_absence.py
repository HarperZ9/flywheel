"""C4a: an absent process record is reported as no record, never as a failure.

A student who never kept a log, or kept a short one, has shown nothing about
their writing either way. `process verify` on a document with no log says so
and exits 3, a code of its own, apart from a tampered or drifted log (exit 1).
An intact verify, an export and a disclosure statement print the same limits
line, and the process summary's does-not-prove line speaks about the record,
not about findings.
"""
import json
import pathlib

import pytest

from articulate import process_events as ev
from articulate import process_export as px
from articulate import process_ledger as pl
from articulate.cli import main
from articulate.tool_text import SCOPE

TEXT = "The rain fell for three days on the low field.\n"


@pytest.fixture
def doc(tmp_path):
    p = tmp_path / "essay.md"
    p.write_text(TEXT, encoding="utf-8")
    return str(p)


def test_no_log_is_no_record_with_its_own_exit_code(doc, capsys):
    assert main(["process", "verify", doc]) == px.NO_RECORD_EXIT == 3
    err = capsys.readouterr().err
    assert "no record for this file. Use other evidence to decide who wrote a text" in err


def test_a_tampered_log_still_exits_1(doc):
    pl.init(doc)
    ev.record_draft(doc, TEXT)
    log = pathlib.Path(pl.paths(doc)["log"])
    log.write_text(log.read_text(encoding="utf-8").replace('"draft"', '"drafx"'),
                   encoding="utf-8")
    assert main(["process", "verify", doc]) == 1


def test_an_intact_verify_prints_the_limits_line(doc, capsys):
    pl.init(doc)
    ev.record_draft(doc, TEXT)
    capsys.readouterr()
    assert main(["process", "verify", doc]) == 0
    cap = capsys.readouterr()
    assert json.loads(cap.out)["limits"] == px.RECORD_LIMITS
    assert px.RECORD_LIMITS in cap.err


def test_export_and_disclose_print_the_limits_line(doc, capsys):
    pl.init(doc)
    ev.record_draft(doc, TEXT)
    capsys.readouterr()
    assert main(["process", "export", doc]) == 0
    assert px.RECORD_LIMITS in capsys.readouterr().out
    assert main(["disclose", doc]) == 0
    cap = capsys.readouterr()
    assert px.RECORD_LIMITS in cap.err and px.RECORD_LIMITS not in cap.out


def test_the_summary_scope_line_speaks_about_the_record(doc):
    pl.init(doc)
    ev.record_draft(doc, TEXT)
    summ = px.summary(doc, [], {}, None)
    assert summ["scope"] != SCOPE
    assert "record" in summ["scope"] and "finding" not in summ["scope"]
