"""Falsifiers for the report in the document that has to carry it.

Five formats render the same rows, so the property worth pinning is the one
they share: worst first, the release next to the verdict, and no authoritative
value anywhere. A format that reordered the rows would put a PASS at the top of
a held answer, which is the one place a reader stops early.
"""
import json
import re

import pytest

from harness.contract_terms import CITED, HOLD, RELEASE, TABLE
from harness.pdf_writer import read_attachment
from harness.report_docs import (as_latex, as_markdown, as_text, render,
                                 tex_escape, worst_first, write_report)
from harness.verdict import Verdict

ANSWER = {"tax": {"value": 4165.50, "source": "irs-2025-rate-schedule-single"}}
REPORT = {
    "verdict": Verdict.FAIL.value,
    "release": HOLD,
    "blocking": ["tax"],
    "checked": 3,
    "passed": 1,
    "fields": [
        {"field": "taxable_income", "authority": CITED, "criticality": "standard",
         "verdict": Verdict.PASS.value, "code": "AGREES",
         "reason": "the answer cites the return"},
        {"field": "note", "authority": CITED, "criticality": "advisory",
         "verdict": Verdict.UNVERIFIABLE.value, "code": "NO_SOURCE",
         "reason": "nothing bound this value"},
        {"field": "tax", "authority": TABLE, "criticality": "critical",
         "verdict": Verdict.FAIL.value, "code": "DISAGREES",
         "reason": "the value disagrees with irs-2025-tax-table-single"},
    ],
    "next": {"fields": [{"field": "tax", "do": "consult the table"}]},
}
PROVEN = dict(REPORT, proof={"verdict": Verdict.FAIL.value, "checker": "lean 4.33.1",
                             "axioms": ["sorryAx"], "errors": [],
                             "reason": "an obligation did not close"})


def test_the_worst_field_comes_first_whatever_the_contract_order_was():
    """An unverified field outranks a passing one even when it is advisory.
    Criticality decides what a non-PASS blocks, never how bad it is."""
    assert [row["field"] for row in worst_first(REPORT)] == \
        ["tax", "note", "taxable_income"]


def test_every_format_opens_on_the_verdict_and_the_release():
    for body in (as_text(REPORT), as_markdown(REPORT), as_latex(REPORT)):
        assert Verdict.FAIL.value in body
        assert HOLD in body


def test_the_blocking_field_is_named_where_the_release_is():
    assert "blocked by: tax" in as_text(REPORT)


def test_no_format_carries_an_authoritative_value():
    """The report says a field disagrees. It never says what the authority
    would have said, because a reader who could copy that number would stop
    consulting the authority."""
    for body in (as_text(REPORT), as_markdown(REPORT), as_latex(REPORT)):
        assert "4169" not in body


def test_the_first_line_of_a_held_report_is_the_field_that_held_it():
    assert as_text(REPORT).splitlines()[2].strip().startswith(Verdict.FAIL.value)


# --- latex ------------------------------------------------------------------

def test_an_underscore_in_a_field_name_is_escaped():
    """`taxable_income` typesets as subscripted nonsense unescaped, and a
    report that misnames its own subject is worse than no report."""
    assert tex_escape("taxable_income") == "taxable" + chr(92) + "_income"
    assert chr(92) + "_income" in as_latex(REPORT)


def test_the_latex_output_is_a_fragment_not_a_document():
    assert "documentclass" not in as_latex(REPORT)


# --- markdown ---------------------------------------------------------------

def test_a_pipe_in_a_reason_does_not_break_the_table():
    """One extra cell boundary shifts every reason one column left, and the
    table still renders, so nothing announces the damage."""
    report = json.loads(json.dumps(REPORT))
    report["fields"][0]["reason"] = "a | b"
    row = [line for line in as_markdown(report).splitlines()
           if "taxable_income" in line][0]
    slash = chr(92)
    unescaped = re.compile("(?<!" + slash + slash + ")" + slash + "|")
    assert len(unescaped.findall(row)) == 6


# --- the proof section ------------------------------------------------------

def test_a_report_with_no_proof_says_nothing_about_one():
    assert "proof" not in as_text(REPORT)


def test_the_kernel_disagreeing_shows_up_in_every_written_format():
    for body in (as_text(PROVEN), as_markdown(PROVEN), as_latex(PROVEN)):
        assert "sorryAx" in body
        assert "lean 4.33.1" in body


# --- dispatch ---------------------------------------------------------------

def test_render_chooses_by_suffix():
    assert render(REPORT, ".md").startswith("# Flywheel")
    assert render(REPORT, ".tex").startswith(chr(92) + "section")
    assert json.loads(render(REPORT, ".json"))["release"] == HOLD
    assert render(REPORT, ".pdf").startswith(b"%PDF")
    assert render(REPORT, "").startswith(Verdict.FAIL.value)


def test_an_unknown_suffix_names_the_formats_that_exist():
    with pytest.raises(ValueError) as caught:
        render(REPORT, ".docx")
    assert ".pdf" in str(caught.value)


def test_write_report_puts_the_answer_inside_the_pdf_it_vouches_for(tmp_path):
    """A page and the values it speaks about travelling separately is how a
    filing ends up attached to the wrong return."""
    path = tmp_path / "report.pdf"
    write_report(REPORT, path, answer=ANSWER)
    assert read_attachment(path.read_bytes()) == ANSWER


def test_write_report_uses_the_suffix_and_writes_text_for_the_rest(tmp_path):
    path = tmp_path / "report.md"
    write_report(REPORT, path)
    assert path.read_text(encoding="utf-8").startswith("# Flywheel")


def test_a_clean_report_says_release_and_names_nothing_as_blocking():
    clean = dict(REPORT, verdict=Verdict.PASS.value, release=RELEASE, blocking=[])
    assert "blocked by" not in as_text(clean)
