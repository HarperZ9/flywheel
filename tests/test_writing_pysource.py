"""Scoring Python source means scoring its PROSE: docstrings and comments.

Phase 1 recorded this gap when the linter scored its own ban-list data tables
as prose. The extractor closes it: string data never reaches the scorer.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import check_writing as CW  # noqa: E402
import writing_profiles as WP  # noqa: E402
import writing_pysource as PS  # noqa: E402

SAMPLE = '''
"""Module docstring with a seamless claim."""
BANNED_DATA = ("utilize", "leverage", "robust")


def f():
    """Function docstring, plain and clean."""
    x = "powerful cutting-edge string literal"  # comment mentions delve
    return x
'''


def test_docstrings_are_extracted():
    prose = PS.prose_of(SAMPLE)
    assert "seamless claim" in prose
    assert "plain and clean" in prose


def test_string_data_is_not_extracted():
    prose = PS.prose_of(SAMPLE)
    assert "utilize" not in prose
    assert "cutting-edge" not in prose


def test_comments_are_extracted():
    assert "delve" in PS.prose_of(SAMPLE)


def test_syntax_error_yields_empty_not_crash():
    assert PS.prose_of("def broken(:") == ""


def test_scoring_the_linters_own_source_flags_no_ban_list_data():
    src = (Path(__file__).resolve().parent.parent / "scripts"
           / "check_writing.py")
    rec = CW.score_file(str(src), WP.load("chat"))
    assert rec["scored"] == "docstrings+comments"
    assert rec["hard"] == [], rec["violations"]


def test_scoring_writing_lists_scores_no_data():
    src = (Path(__file__).resolve().parent.parent / "scripts"
           / "writing_lists.py")
    rec = CW.score_file(str(src), WP.load("chat"))
    assert rec["hard"] == [], rec["violations"]
