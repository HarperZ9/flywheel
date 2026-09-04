"""Falsifiers for taking an answer out of the document it arrived in.

The risk this feature adds is a number that came from the wrong place. A memo
holds several code blocks and only one of them is the answer; a filing comments
the block out so it does not typeset; a PDF from somewhere else holds a page
that looks like a report and carries nothing a checker may read. Each of those
has a wrong reading that would still produce a plausible report, so each one is
pinned here.
"""
import json

import pytest

from harness.answer_docs import (DocumentError, from_latex, from_markdown,
                                 from_pdf, read_answer)
from harness.pdf_writer import pdf_bytes, read_attachment, wrap

ANSWER = {"tax": {"value": 4169, "source": "irs-2025-tax-table-single"}}
BODY = json.dumps(ANSWER, indent=2)
BACKSLASH = chr(92)


def latex_document(inner: str) -> str:
    return (BACKSLASH + "begin{flywheelanswer}\n" + inner + "\n"
            + BACKSLASH + "end{flywheelanswer}\n")


# --- markdown ---------------------------------------------------------------

def test_the_marked_fence_wins_over_an_earlier_json_fence():
    """A memo shows the reader an illustration first and the answer second.
    Taking the first `json` fence would check the illustration."""
    text = ("# 2025 return\n\n```json\n{\"decoy\": 1}\n```\n\n"
            "```flywheel-answer\n" + BODY + "\n```\n")
    assert from_markdown(text) == ANSWER


def test_a_json_fence_is_read_when_nothing_is_marked():
    assert from_markdown("```json\n" + BODY + "\n```\n") == ANSWER


def test_a_json_fence_that_is_not_an_object_is_skipped_not_accepted():
    text = "```json\n[1, 2, 3]\n```\n\n```json\n" + BODY + "\n```\n"
    assert from_markdown(text) == ANSWER


def test_a_document_with_no_answer_block_is_refused():
    with pytest.raises(DocumentError):
        from_markdown("Just prose about a tax return of 4169 dollars.\n")


def test_prose_holding_the_number_is_never_mined():
    """The failure the whole feature exists to prevent: a value lifted out of a
    sentence would arrive wearing a checker's authority."""
    with pytest.raises(DocumentError):
        from_markdown("The tax is 4169 per irs-2025-tax-table-single.\n")


# --- latex ------------------------------------------------------------------

def test_a_commented_environment_reaches_the_parser():
    """An author who must keep the block out of the typeset page comments it
    line by line. That is still the answer."""
    inner = "\n".join("% " + line for line in BODY.splitlines())
    assert from_latex(latex_document(inner)) == ANSWER


def test_a_verbatim_wrapper_is_unwrapped():
    inner = (BACKSLASH + "begin{verbatim}\n" + BODY + "\n"
             + BACKSLASH + "end{verbatim}")
    assert from_latex(latex_document(inner)) == ANSWER


def test_a_filing_with_no_environment_is_refused():
    with pytest.raises(DocumentError):
        from_latex(BACKSLASH + "section{Return}\nProse.\n")


# --- pdf --------------------------------------------------------------------

def test_a_flywheel_pdf_carries_its_answer_back_out():
    assert from_pdf(pdf_bytes("A return.", attachment=ANSWER)) == ANSWER


def test_a_pdf_with_no_attachment_is_refused_rather_than_read_off_the_page():
    """Reconstructing values from a rendered layout is a guess, and a wrong
    reconstruction reads exactly like a right one."""
    with pytest.raises(DocumentError):
        from_pdf(pdf_bytes("tax 4169"))


def test_a_foreign_pdf_reports_no_attachment_instead_of_raising():
    assert read_attachment(b"%PDF-1.4\ntrailer\n%%EOF\n") is None


def test_the_pdf_is_byte_identical_across_two_writes():
    """A report that hashes differently every time cannot go in a receipt."""
    assert pdf_bytes("A return.", attachment=ANSWER) == \
        pdf_bytes("A return.", attachment=ANSWER)


def test_no_creation_date_is_written():
    assert b"/CreationDate" not in pdf_bytes("A return.")


def test_long_lines_wrap_rather_than_running_off_the_page():
    lines = wrap("word " * 60)
    assert len(lines) > 1
    assert all(len(line) <= 93 for line in lines)
    assert " ".join(lines).split() == ("word " * 60).split()


# --- the dispatcher ---------------------------------------------------------

def test_read_answer_picks_the_reader_from_the_suffix(tmp_path):
    plain = tmp_path / "answer.json"
    plain.write_text(BODY, encoding="utf-8")
    memo = tmp_path / "memo.md"
    memo.write_text("```flywheel-answer\n" + BODY + "\n```\n", encoding="utf-8")
    filing = tmp_path / "filing.tex"
    filing.write_text(latex_document(BODY), encoding="utf-8")
    page = tmp_path / "filed.pdf"
    page.write_bytes(pdf_bytes("A return.", attachment=ANSWER))
    for path in (plain, memo, filing, page):
        assert read_answer(path) == ANSWER, path.suffix


def test_an_unknown_suffix_names_the_ones_that_are_known(tmp_path):
    path = tmp_path / "answer.docx"
    path.write_text("anything", encoding="utf-8")
    with pytest.raises(DocumentError) as caught:
        read_answer(path)
    assert ".tex" in str(caught.value)


def test_an_answer_that_is_a_list_is_refused(tmp_path):
    path = tmp_path / "answer.json"
    path.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(DocumentError):
        read_answer(path)
